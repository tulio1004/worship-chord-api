"""YouTube audio downloader using yt-dlp."""

import subprocess
import logging
import json
import re
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class DownloadResult:
    audio_path: Path
    title: Optional[str]
    artist: Optional[str]
    duration_seconds: Optional[float]
    thumbnail_url: Optional[str] = None


class YouTubeDownloadError(Exception):
    pass


class YouTubeDownloader:
    """Downloads audio from YouTube using yt-dlp."""

    def download(
        self,
        url: str,
        output_dir: Path,
        max_duration: int = 600,
    ) -> DownloadResult:
        """
        Download audio from a YouTube URL.
        Returns path to the raw downloaded audio and metadata.
        """
        logger.info(f"Downloading YouTube audio: {url}")

        # First fetch metadata without downloading
        meta = self._fetch_metadata(url)

        duration = meta.get("duration")
        if duration and duration > max_duration:
            raise YouTubeDownloadError(
                f"Video duration {duration}s exceeds maximum {max_duration}s"
            )

        output_template = str(output_dir / "%(id)s.%(ext)s")

        cmd = [
            "yt-dlp",
            "--no-playlist",
            "--format", "bestaudio/best",
            "--output", output_template,
            "--no-progress",
            "--quiet",
            # Use Android client to bypass YouTube bot detection on server IPs.
            # Android player client doesn't require JS runtime or cookies.
            "--extractor-args", "youtube:player_client=android,web",
            url,
        ]

        logger.debug(f"yt-dlp command: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise YouTubeDownloadError("Download timed out after 120 seconds")
        except FileNotFoundError:
            raise YouTubeDownloadError(
                "yt-dlp not found. Install it with: pip install yt-dlp"
            )

        if result.returncode != 0:
            err = result.stderr.strip() or result.stdout.strip()
            logger.error(f"yt-dlp failed: {err}")
            raise YouTubeDownloadError(f"Download failed: {err[:300]}")

        # Find the downloaded file
        audio_files = list(output_dir.glob("*.*"))
        audio_files = [
            f for f in audio_files
            if f.suffix.lower() in (".webm", ".m4a", ".mp3", ".opus", ".ogg", ".wav", ".flac", ".aac")
        ]

        if not audio_files:
            raise YouTubeDownloadError("yt-dlp succeeded but no audio file found in output directory")

        audio_path = max(audio_files, key=lambda f: f.stat().st_size)
        logger.info(f"Downloaded audio to: {audio_path} ({audio_path.stat().st_size // 1024} KB)")

        title = meta.get("title") or meta.get("fulltitle")
        uploader = meta.get("uploader") or meta.get("channel")

        return DownloadResult(
            audio_path=audio_path,
            title=title,
            artist=uploader,
            duration_seconds=float(duration) if duration else None,
        )

    def _fetch_metadata(self, url: str) -> dict:
        """Fetch video metadata without downloading."""
        cmd = [
            "yt-dlp",
            "--dump-json",
            "--no-playlist",
            "--quiet",
            "--extractor-args", "youtube:player_client=android,web",
            url,
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                return json.loads(result.stdout.strip())
        except Exception as e:
            logger.warning(f"Could not fetch metadata: {e}")
        return {}
