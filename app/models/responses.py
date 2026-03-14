from pydantic import BaseModel
from typing import Optional, List, Any


class ErrorDetail(BaseModel):
    code: str
    message: str


class ChordEvent(BaseModel):
    start: float
    end: float
    label: str
    raw_label: str
    confidence: Optional[float] = None


class TranscriptionSegment(BaseModel):
    start: float
    end: float
    text: str


class TranscriptionResult(BaseModel):
    source: str  # "provided" or "generated"
    raw_text: str
    cleaned_text: str
    segments: List[TranscriptionSegment]


class ActiveChord(BaseModel):
    position_hint: int
    label: str


class AlignmentBlock(BaseModel):
    start: float
    end: float
    lyric: str
    active_chords: List[ActiveChord]
    display_line: str


class AlignmentResult(BaseModel):
    method: str
    blocks: List[AlignmentBlock]


class AudioInfo(BaseModel):
    sample_rate: int
    channels: int
    format: str


class MetadataInfo(BaseModel):
    title: Optional[str]
    artist: Optional[str]
    duration_seconds: Optional[float]


class InputInfo(BaseModel):
    youtube_url: Optional[str] = None
    used_provided_transcription: bool
    language: Optional[str]


class Diagnostics(BaseModel):
    warnings: List[str]
    processing_seconds: float
    download_engine: Optional[str]
    chord_engine: str
    transcription_engine: str


class ProcessResponse(BaseModel):
    success: bool
    input: InputInfo
    metadata: MetadataInfo
    audio: AudioInfo
    chords: List[ChordEvent]
    transcription: TranscriptionResult
    alignment: AlignmentResult
    diagnostics: Diagnostics


class ErrorResponse(BaseModel):
    success: bool = False
    error: ErrorDetail
