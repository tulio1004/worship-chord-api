"""API route definitions."""

import logging
import time
from pathlib import Path
from typing import Optional
from io import BytesIO

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, status
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.models.requests import ProcessYouTubeRequest, AlignRequest
from app.models.responses import (
    ProcessResponse,
    ErrorResponse,
    ErrorDetail,
    ChordEvent as ChordEventModel,
    TranscriptionResult,
    TranscriptionSegment as TranscriptionSegmentModel,
    AlignmentResult,
    AlignmentBlock as AlignmentBlockModel,
    ActiveChord,
    AudioInfo as AudioInfoModel,
    MetadataInfo,
    InputInfo,
    Diagnostics,
)
from app.services.downloader import YouTubeDownloader, YouTubeDownloadError
from app.services.audio import AudioService, AudioConversionError
from app.services.chords import create_chord_service
from app.services.transcription import create_transcription_service
from app.services.alignment import align
from app.services.cleanup import LyricCleanupService
from app.services.metadata import merge_metadata
from app.utils.file_utils import temp_workspace

router = APIRouter()
logger = logging.getLogger(__name__)

# Shared service instances (initialized once)
_downloader = YouTubeDownloader()
_audio_service = AudioService()
_chord_service = create_chord_service(settings.chord_engine)
_transcription_service = create_transcription_service(
    engine_name="faster-whisper",
    model_size=settings.whisper_model_size,
    device=settings.whisper_device,
    compute_type=settings.whisper_compute_type,
)
_cleanup_service = LyricCleanupService()


def _error(code: str, message: str, status_code: int = 400) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(error=ErrorDetail(code=code, message=message)).model_dump(),
    )


def _build_process_response(
    *,
    workspace: Path,
    youtube_url: Optional[str],
    audio_path: Path,
    audio_info,
    request_language: Optional[str],
    provided_transcription: Optional[str],
    prefer_sharp_keys: bool,
    cleanup_lyrics: bool,
    title: Optional[str] = None,
    artist: Optional[str] = None,
    downloaded_title: Optional[str] = None,
    downloaded_artist: Optional[str] = None,
    downloaded_duration: Optional[float] = None,
    download_engine: Optional[str],
    start_time: float,
) -> ProcessResponse:
    warnings = []

    # --- Chord extraction ---
    try:
        chord_events = _chord_service.extract(audio_path, prefer_sharps=prefer_sharp_keys)
    except Exception as e:
        logger.warning(f"Chord extraction failed: {e}")
        chord_events = []
        warnings.append(f"Chord extraction failed: {e}")

    # --- Transcription ---
    if provided_transcription:
        transcription_output = _transcription_service.from_provided_text(provided_transcription)
        used_provided = True
    else:
        try:
            transcription_output = _transcription_service.transcribe(
                audio_path, language=request_language
            )
        except Exception as e:
            logger.warning(f"Transcription failed: {e}")
            transcription_output = None
            warnings.append(f"Transcription failed: {e}")
        used_provided = False

    raw_text = transcription_output.raw_text if transcription_output else ""
    cleaned_text = _cleanup_service.clean(raw_text, apply_cleanup=cleanup_lyrics)
    segments = transcription_output.segments if transcription_output else []
    transcription_engine = transcription_output.engine if transcription_output else "none"
    detected_lang = (transcription_output.language if transcription_output else None) or request_language

    # --- Alignment ---
    alignment_blocks = align(chord_events, segments) if chord_events and segments else []

    # --- Metadata ---
    meta = merge_metadata(
        downloaded_title=downloaded_title,
        downloaded_artist=downloaded_artist,
        downloaded_duration=downloaded_duration or audio_info.duration_seconds,
        provided_title=title,
        provided_artist=artist,
    )

    processing_seconds = round(time.time() - start_time, 2)

    # --- Build response models ---
    chord_models = [
        ChordEventModel(
            start=c.start, end=c.end, label=c.label,
            raw_label=c.raw_label, confidence=c.confidence
        )
        for c in chord_events
    ]

    seg_models = [
        TranscriptionSegmentModel(start=s.start, end=s.end, text=s.text)
        for s in segments
    ]

    block_models = [
        AlignmentBlockModel(
            start=b.start,
            end=b.end,
            lyric=b.lyric,
            active_chords=[
                ActiveChord(position_hint=h.position_hint, label=h.label)
                for h in b.active_chords
            ],
            display_line=b.display_line,
        )
        for b in alignment_blocks
    ]

    return ProcessResponse(
        success=True,
        input=InputInfo(
            youtube_url=youtube_url,
            used_provided_transcription=used_provided,
            language=detected_lang,
        ),
        metadata=MetadataInfo(
            title=meta.title,
            artist=meta.artist,
            duration_seconds=meta.duration_seconds,
        ),
        audio=AudioInfoModel(
            sample_rate=audio_info.sample_rate,
            channels=audio_info.channels,
            format=audio_info.format,
        ),
        chords=chord_models,
        transcription=TranscriptionResult(
            source="provided" if used_provided else "generated",
            raw_text=raw_text,
            cleaned_text=cleaned_text,
            segments=seg_models,
        ),
        alignment=AlignmentResult(
            method="timestamp_overlap_v1",
            blocks=block_models,
        ),
        diagnostics=Diagnostics(
            warnings=warnings,
            processing_seconds=processing_seconds,
            download_engine=download_engine,
            chord_engine=_chord_service.engine_name,
            transcription_engine=transcription_engine,
        ),
    )


@router.get("/health")
async def health():
    return {
        "status": "ok",
        "version": settings.version,
        "app": settings.app_name,
        "environment": settings.environment,
        "chord_engine": settings.chord_engine,
        "whisper_model": settings.whisper_model_size,
    }


@router.post("/process-youtube")
async def process_youtube(request: ProcessYouTubeRequest):
    start_time = time.time()
    logger.info(f"Processing YouTube URL: {request.youtube_url}")

    with temp_workspace() as workspace:
        # Download
        try:
            download_result = _downloader.download(
                url=request.youtube_url,
                output_dir=workspace,
                max_duration=settings.max_audio_duration_seconds,
            )
        except YouTubeDownloadError as e:
            return _error("DOWNLOAD_FAILED", str(e), 422)
        except Exception as e:
            logger.exception("Unexpected download error")
            return _error("DOWNLOAD_ERROR", str(e), 500)

        # Normalize audio
        try:
            audio_info = _audio_service.normalize(
                input_path=download_result.audio_path,
                output_dir=workspace,
            )
        except AudioConversionError as e:
            return _error("AUDIO_CONVERSION_FAILED", str(e), 422)
        except Exception as e:
            logger.exception("Unexpected audio conversion error")
            return _error("AUDIO_ERROR", str(e), 500)

        try:
            response = _build_process_response(
                workspace=workspace,
                youtube_url=request.youtube_url,
                audio_path=audio_info.path,
                audio_info=audio_info,
                request_language=request.language,
                provided_transcription=request.transcription,
                prefer_sharp_keys=request.prefer_sharp_keys,
                cleanup_lyrics=request.cleanup_lyrics,
                title=request.title,
                artist=request.artist,
                downloaded_title=download_result.title,
                downloaded_artist=download_result.artist,
                downloaded_duration=download_result.duration_seconds,
                download_engine="yt-dlp",
                start_time=start_time,
            )
        except Exception as e:
            logger.exception("Error during processing")
            return _error("PROCESSING_ERROR", str(e), 500)

    return response


@router.post("/process-audio")
async def process_audio(
    file: UploadFile = File(...),
    language: Optional[str] = Form(default=None),
    transcription: Optional[str] = Form(default=None),
    title: Optional[str] = Form(default=None),
    artist: Optional[str] = Form(default=None),
    prefer_sharp_keys: bool = Form(default=True),
    cleanup_lyrics: bool = Form(default=True),
):
    start_time = time.time()
    logger.info(f"Processing uploaded audio: {file.filename}")

    allowed_extensions = {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".webm", ".opus", ".aac"}
    suffix = Path(file.filename or "audio.wav").suffix.lower()
    if suffix not in allowed_extensions:
        return _error("UNSUPPORTED_FORMAT", f"Unsupported audio format: {suffix}", 422)

    with temp_workspace() as workspace:
        input_path = workspace / f"upload{suffix}"
        content = await file.read()
        if not content:
            return _error("EMPTY_FILE", "Uploaded file is empty", 422)
        input_path.write_bytes(content)

        try:
            audio_info = _audio_service.normalize(input_path=input_path, output_dir=workspace)
        except AudioConversionError as e:
            return _error("AUDIO_CONVERSION_FAILED", str(e), 422)
        except Exception as e:
            logger.exception("Unexpected audio error")
            return _error("AUDIO_ERROR", str(e), 500)

        if audio_info.duration_seconds > settings.max_audio_duration_seconds:
            return _error(
                "DURATION_EXCEEDED",
                f"Audio duration {audio_info.duration_seconds:.0f}s exceeds maximum {settings.max_audio_duration_seconds}s",
                422,
            )

        try:
            response = _build_process_response(
                workspace=workspace,
                youtube_url=None,
                audio_path=audio_info.path,
                audio_info=audio_info,
                request_language=language,
                provided_transcription=transcription,
                prefer_sharp_keys=prefer_sharp_keys,
                cleanup_lyrics=cleanup_lyrics,
                title=title,
                artist=artist,
                downloaded_title=None,
                downloaded_artist=None,
                downloaded_duration=audio_info.duration_seconds,
                download_engine=None,
                start_time=start_time,
            )
        except Exception as e:
            logger.exception("Error during processing")
            return _error("PROCESSING_ERROR", str(e), 500)

    return response


@router.post("/extract-chords")
async def extract_chords_endpoint(
    file: UploadFile = File(...),
    prefer_sharp_keys: bool = Form(default=True),
):
    """Extract chords from an uploaded audio file."""
    start_time = time.time()
    suffix = Path(file.filename or "audio.wav").suffix.lower()

    with temp_workspace() as workspace:
        input_path = workspace / f"upload{suffix}"
        content = await file.read()
        if not content:
            return _error("EMPTY_FILE", "Uploaded file is empty", 422)
        input_path.write_bytes(content)

        try:
            audio_info = _audio_service.normalize(input_path=input_path, output_dir=workspace)
            chord_events = _chord_service.extract(audio_info.path, prefer_sharps=prefer_sharp_keys)
        except Exception as e:
            logger.exception("Chord extraction error")
            return _error("CHORD_EXTRACTION_FAILED", str(e), 500)

        return {
            "success": True,
            "chord_engine": _chord_service.engine_name,
            "duration_seconds": audio_info.duration_seconds,
            "chords": [
                {"start": c.start, "end": c.end, "label": c.label, "raw_label": c.raw_label}
                for c in chord_events
            ],
            "processing_seconds": round(time.time() - start_time, 2),
        }


@router.post("/transcribe")
async def transcribe_endpoint(
    file: UploadFile = File(...),
    language: Optional[str] = Form(default=None),
    cleanup: bool = Form(default=True),
):
    """Transcribe an uploaded audio file."""
    start_time = time.time()
    suffix = Path(file.filename or "audio.wav").suffix.lower()

    with temp_workspace() as workspace:
        input_path = workspace / f"upload{suffix}"
        content = await file.read()
        if not content:
            return _error("EMPTY_FILE", "Uploaded file is empty", 422)
        input_path.write_bytes(content)

        try:
            audio_info = _audio_service.normalize(input_path=input_path, output_dir=workspace)
            result = _transcription_service.transcribe(audio_info.path, language=language)
        except Exception as e:
            logger.exception("Transcription error")
            return _error("TRANSCRIPTION_FAILED", str(e), 500)

        cleaned = _cleanup_service.clean(result.raw_text, apply_cleanup=cleanup)

        return {
            "success": True,
            "engine": result.engine,
            "language": result.language,
            "raw_text": result.raw_text,
            "cleaned_text": cleaned,
            "segments": [
                {"start": s.start, "end": s.end, "text": s.text}
                for s in result.segments
            ],
            "processing_seconds": round(time.time() - start_time, 2),
        }
