from pydantic import BaseModel, HttpUrl, field_validator
from typing import Optional


class ProcessYouTubeRequest(BaseModel):
    youtube_url: str
    transcription: Optional[str] = None
    language: Optional[str] = None
    title: Optional[str] = None
    artist: Optional[str] = None
    prefer_sharp_keys: bool = True
    cleanup_lyrics: bool = True

    @field_validator("youtube_url")
    @classmethod
    def validate_youtube_url(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("youtube_url cannot be empty")
        valid_hosts = ("youtube.com", "youtu.be", "www.youtube.com", "m.youtube.com")
        from urllib.parse import urlparse
        parsed = urlparse(v)
        if not any(parsed.netloc.endswith(host) for host in valid_hosts):
            raise ValueError(f"Not a valid YouTube URL: {v}")
        return v


class ExtractChordsRequest(BaseModel):
    audio_url: Optional[str] = None
    prefer_sharp_keys: bool = True


class TranscribeRequest(BaseModel):
    audio_url: Optional[str] = None
    language: Optional[str] = None
    cleanup: bool = True


class AlignRequest(BaseModel):
    chords: list
    segments: list
    prefer_sharp_keys: bool = True
