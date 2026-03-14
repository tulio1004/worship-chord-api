import pytest
from pydantic import ValidationError
from app.models.requests import ProcessYouTubeRequest


def test_valid_youtube_url():
    req = ProcessYouTubeRequest(youtube_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert req.youtube_url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def test_valid_youtu_be_url():
    req = ProcessYouTubeRequest(youtube_url="https://youtu.be/dQw4w9WgXcQ")
    assert "youtu.be" in req.youtube_url


def test_invalid_url_raises():
    with pytest.raises(ValidationError):
        ProcessYouTubeRequest(youtube_url="https://vimeo.com/12345")


def test_empty_url_raises():
    with pytest.raises(ValidationError):
        ProcessYouTubeRequest(youtube_url="")


def test_defaults():
    req = ProcessYouTubeRequest(youtube_url="https://youtu.be/abc123")
    assert req.prefer_sharp_keys is True
    assert req.cleanup_lyrics is True
    assert req.language is None
    assert req.transcription is None
