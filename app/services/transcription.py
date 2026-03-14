"""
Transcription service with abstract interface.
Default: faster-whisper (CPU int8). Falls back gracefully.
"""

import logging
from pathlib import Path
from typing import List, Optional, Protocol, runtime_checkable
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class TranscriptionSegment:
    start: float
    end: float
    text: str


@dataclass
class TranscriptionOutput:
    raw_text: str
    segments: List[TranscriptionSegment]
    language: Optional[str]
    engine: str


@runtime_checkable
class TranscriptionEngine(Protocol):
    def transcribe(
        self,
        audio_path: Path,
        language: Optional[str] = None,
    ) -> TranscriptionOutput:
        ...

    @property
    def engine_name(self) -> str:
        ...


class FasterWhisperEngine:
    """
    Transcription using faster-whisper.
    Uses CPU + int8 quantization for Railway compatibility.
    """

    def __init__(
        self,
        model_size: str = "base",
        device: str = "cpu",
        compute_type: str = "int8",
    ):
        self._model_size = model_size
        self._device = device
        self._compute_type = compute_type
        self._model = None

    @property
    def engine_name(self) -> str:
        return f"faster-whisper({self._model_size})"

    def _load_model(self):
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
                logger.info(
                    f"Loading faster-whisper model: {self._model_size} "
                    f"({self._device}/{self._compute_type})"
                )
                self._model = WhisperModel(
                    self._model_size,
                    device=self._device,
                    compute_type=self._compute_type,
                )
                logger.info("faster-whisper model loaded")
            except ImportError:
                raise RuntimeError(
                    "faster-whisper is not installed. Run: pip install faster-whisper"
                )

    def transcribe(
        self,
        audio_path: Path,
        language: Optional[str] = None,
    ) -> TranscriptionOutput:
        self._load_model()
        logger.info(f"Transcribing: {audio_path.name} (language={language or 'auto'})")

        lang_arg = language if language and language != "auto" else None

        segments_raw, info = self._model.transcribe(
            str(audio_path),
            language=lang_arg,
            beam_size=5,
            word_timestamps=False,
            vad_filter=False,                       # VAD drops music — keep off
            temperature=[0, 0.2, 0.4, 0.6, 0.8, 1.0],  # retry with higher temp when segment looks bad
            condition_on_previous_text=False,       # CRITICAL: prevents hallucination loops in music
            compression_ratio_threshold=2.4,        # discard segments with excessive repetition
            log_prob_threshold=-1.0,
            no_speech_threshold=0.6,
        )

        segments: List[TranscriptionSegment] = []
        text_parts: List[str] = []

        for seg in segments_raw:
            text = seg.text.strip()
            if text:
                segments.append(TranscriptionSegment(
                    start=round(seg.start, 3),
                    end=round(seg.end, 3),
                    text=text,
                ))
                text_parts.append(text)

        raw_text = " ".join(text_parts)
        detected_lang = getattr(info, "language", None)

        logger.info(
            f"Transcription done: {len(segments)} segments, "
            f"language={detected_lang}, chars={len(raw_text)}"
        )

        return TranscriptionOutput(
            raw_text=raw_text,
            segments=segments,
            language=detected_lang,
            engine=self.engine_name,
        )


class OpenAIWhisperEngine:
    """
    Fallback: openai-whisper (original implementation).
    Heavier but works without CTranslate2.
    """

    def __init__(self, model_size: str = "base"):
        self._model_size = model_size
        self._model = None

    @property
    def engine_name(self) -> str:
        return f"openai-whisper({self._model_size})"

    def _load_model(self):
        if self._model is None:
            try:
                import whisper
                logger.info(f"Loading openai-whisper model: {self._model_size}")
                self._model = whisper.load_model(self._model_size)
                logger.info("openai-whisper model loaded")
            except ImportError:
                raise RuntimeError(
                    "openai-whisper is not installed. Run: pip install openai-whisper"
                )

    def transcribe(
        self,
        audio_path: Path,
        language: Optional[str] = None,
    ) -> TranscriptionOutput:
        self._load_model()
        import whisper

        options = {}
        if language and language != "auto":
            options["language"] = language

        logger.info(f"Transcribing with openai-whisper: {audio_path.name}")
        result = self._model.transcribe(str(audio_path), **options)

        segments: List[TranscriptionSegment] = []
        for seg in result.get("segments", []):
            text = seg["text"].strip()
            if text:
                segments.append(TranscriptionSegment(
                    start=round(seg["start"], 3),
                    end=round(seg["end"], 3),
                    text=text,
                ))

        return TranscriptionOutput(
            raw_text=result.get("text", "").strip(),
            segments=segments,
            language=result.get("language"),
            engine=self.engine_name,
        )


class TranscriptionService:
    """Facade for transcription engines."""

    def __init__(self, engine: TranscriptionEngine):
        self._engine = engine

    @property
    def engine_name(self) -> str:
        return self._engine.engine_name

    def transcribe(
        self,
        audio_path: Path,
        language: Optional[str] = None,
    ) -> TranscriptionOutput:
        return self._engine.transcribe(audio_path, language=language)

    def from_provided_text(self, text: str) -> TranscriptionOutput:
        """Wrap a caller-provided transcription in the standard output format."""
        # Split into rough segments (no timestamps available)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        segments = []
        # Without real timestamps, place them evenly — downstream will handle alignment by text
        for i, line in enumerate(lines):
            segments.append(TranscriptionSegment(
                start=float(i),
                end=float(i + 1),
                text=line,
            ))
        return TranscriptionOutput(
            raw_text=text,
            segments=segments,
            language=None,
            engine="provided",
        )


def create_transcription_service(
    engine_name: str = "faster-whisper",
    model_size: str = "base",
    device: str = "cpu",
    compute_type: str = "int8",
) -> TranscriptionService:
    if engine_name == "faster-whisper":
        return TranscriptionService(FasterWhisperEngine(model_size, device, compute_type))
    elif engine_name == "openai-whisper":
        return TranscriptionService(OpenAIWhisperEngine(model_size))
    raise ValueError(f"Unknown transcription engine: {engine_name!r}")
