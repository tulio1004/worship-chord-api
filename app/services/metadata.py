"""Metadata extraction and merging service."""

import logging
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SongMetadata:
    title: Optional[str]
    artist: Optional[str]
    duration_seconds: Optional[float]


def merge_metadata(
    downloaded_title: Optional[str],
    downloaded_artist: Optional[str],
    downloaded_duration: Optional[float],
    provided_title: Optional[str],
    provided_artist: Optional[str],
) -> SongMetadata:
    """
    Merge caller-provided metadata with downloaded metadata.
    Caller-provided values take priority.
    """
    title = provided_title or downloaded_title
    artist = provided_artist or downloaded_artist

    # Attempt to parse 'Artist - Title' from YouTube title if artist not known
    if title and not artist and " - " in title:
        parts = title.split(" - ", 1)
        artist = parts[0].strip()
        title = parts[1].strip()

    return SongMetadata(
        title=title,
        artist=artist,
        duration_seconds=downloaded_duration,
    )
