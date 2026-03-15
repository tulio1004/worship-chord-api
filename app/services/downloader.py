"""YouTube audio downloader.

Strategy (tried in order):
  1. CobaltDownloader — cobalt.tools is a purpose-built media downloader with
     a free public API. It handles YouTube extraction on its own servers and
     returns a direct stream URL, bypassing Railway's IP block entirely.
  2. YtDlpDownloader  — fallback; works on non-flagged IPs (local dev).
"""

import re
import subprocess
import logging
import json
import tempfile
import os
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Shared data types
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DownloadResult:
    audio_path: Path
    title: Optional[str]
    artist: Optional[str]
    duration_seconds: Optional[float]
    thumbnail_url: Optional[str] = None


class YouTubeDownloadError(Exception):
    pass


_VIDEO_ID_RE = re.compile(
    r'(?:v=|youtu\.be/|embed/|shorts/)([a-zA-Z0-9_-]{11})'
)

def _extract_video_id(url: str) -> str:
    m = _VIDEO_ID_RE.search(url)
    if not m:
        raise YouTubeDownloadError(f"Cannot extract YouTube video ID from: {url}")
    return m.group(1)


# ─────────────────────────────────────────────────────────────────────────────
# Strategy 1: cobalt.tools API
# ─────────────────────────────────────────────────────────────────────────────

class CobaltDownloader:
    """
    Uses the cobalt.tools public API to download YouTube audio.

    cobalt is a purpose-built media downloader that runs its own extraction
    infrastructure. It accepts a YouTube URL and returns a direct stream link,
    so Railway never touches YouTube's extraction API (no bot detection).

    API docs: https://github.com/imputnet/cobalt
    """

    API_URL = "https://api.cobalt.tools/"

    def download(
        self,
        url: str,
        output_dir: Path,
        max_duration: int = 600,
    ) -> DownloadResult:
        video_id = _extract_video_id(url)
        logger.info(f"Requesting cobalt.tools for video: {video_id}")

        with httpx.Client(timeout=30, follow_redirects=True) as client:
            resp = client.post(
                self.API_URL,
                json={"url": url, "downloadMode": "audio"},
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        status = data.get("status")
        if status == "error":
            code = data.get("error", {}).get("code", "unknown")
            raise RuntimeError(f"cobalt error: {code}")
        if status not in ("tunnel", "redirect", "stream"):
            raise RuntimeError(f"Unexpected cobalt status: {status!r}")

        audio_url = data["url"]

        # Parse title from filename hint if cobalt includes it
        filename_hint = data.get("filename") or f"{video_id}.m4a"
        ext = Path(filename_hint).suffix.lstrip(".") or "m4a"
        output_path = output_dir / f"{video_id}.{ext}"

        logger.info(f"cobalt: streaming audio ({status}) → {output_path.name}")

        with httpx.Client(timeout=180, follow_redirects=True) as dl_client:
            with dl_client.stream("GET", audio_url) as stream:
                stream.raise_for_status()
                with open(output_path, "wb") as f:
                    for chunk in stream.iter_bytes(chunk_size=65536):
                        f.write(chunk)

        size_kb = output_path.stat().st_size // 1024
        logger.info(f"cobalt: downloaded {size_kb} KB")

        # cobalt doesn't return structured metadata — title comes from filename
        raw_title = Path(filename_hint).stem.replace("_", " ").replace("-", " ")
        title = raw_title if raw_title != video_id else None

        return DownloadResult(
            audio_path=output_path,
            title=title or None,
            artist=None,
            duration_seconds=None,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Strategy 2: yt-dlp (fallback)
# ─────────────────────────────────────────────────────────────────────────────

def _cookies_args() -> list[str]:
    """Return --cookies <tmpfile> args if YOUTUBE_COOKIES env var is set."""
    from app.core.config import settings
    cookies = settings.youtube_cookies.strip()
    if not cookies:
        return []
    fd, path = tempfile.mkstemp(suffix=".txt", prefix="yt_cookies_")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(cookies)
    except Exception:
        os.unlink(path)
        raise
    return ["--cookies", path]


class YtDlpDownloader:
    """yt-dlp downloader — works on non-flagged IPs (e.g. local dev)."""

    def download(
        self,
        url: str,
        output_dir: Path,
        max_duration: int = 600,
    ) -> DownloadResult:
        logger.info(f"Trying yt-dlp for: {url}")
        meta = self._fetch_metadata(url)

        duration = meta.get("duration")
        if duration and duration > max_duration:
            raise YouTubeDownloadError(
                f"Video duration {duration}s exceeds maximum {max_duration}s"
            )

        output_template = str(output_dir / "%(id)s.%(ext)s")
        cookies_args = _cookies_args()

        cmd = [
            "yt-dlp",
            "--no-playlist",
            "--format", "bestaudio/best",
            "--output", output_template,
            "--no-progress",
            "--quiet",
        ] + cookies_args + [url]

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120, check=False,
            )
        except subprocess.TimeoutExpired:
            raise YouTubeDownloadError("yt-dlp timed out after 120 seconds")
        except FileNotFoundError:
            raise YouTubeDownloadError("yt-dlp not found")

        if result.returncode != 0:
            err = result.stderr.strip() or result.stdout.strip()
            logger.error(f"yt-dlp failed: {err}")
            raise YouTubeDownloadError(f"yt-dlp: {err[:300]}")

        audio_files = [
            f for f in output_dir.glob("*.*")
            if f.suffix.lower() in (".webm", ".m4a", ".mp3", ".opus", ".ogg", ".wav", ".flac", ".aac")
        ]
        if not audio_files:
            raise YouTubeDownloadError("yt-dlp succeeded but no audio file found")

        audio_path = max(audio_files, key=lambda f: f.stat().st_size)
        logger.info(f"yt-dlp: {audio_path.name} ({audio_path.stat().st_size // 1024} KB)")

        return DownloadResult(
            audio_path=audio_path,
            title=meta.get("title") or meta.get("fulltitle"),
            artist=meta.get("uploader") or meta.get("channel"),
            duration_seconds=float(duration) if duration else None,
        )

    def _fetch_metadata(self, url: str) -> dict:
        cookies_args = _cookies_args()
        cmd = [
            "yt-dlp", "--dump-json", "--no-playlist", "--quiet",
        ] + cookies_args + [url]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30, check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                return json.loads(result.stdout.strip())
        except Exception as e:
            logger.warning(f"yt-dlp metadata fetch failed: {e}")
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# Facade: cobalt → yt-dlp
# ─────────────────────────────────────────────────────────────────────────────

class YouTubeDownloader:
    """Tries cobalt.tools first, falls back to yt-dlp."""

    def __init__(self):
        self._cobalt = CobaltDownloader()
        self._ytdlp = YtDlpDownloader()

    def download(
        self,
        url: str,
        output_dir: Path,
        max_duration: int = 600,
    ) -> DownloadResult:
        try:
            return self._cobalt.download(url, output_dir, max_duration)
        except YouTubeDownloadError:
            raise
        except Exception as e:
            logger.warning(f"cobalt failed ({e}), falling back to yt-dlp")

        return self._ytdlp.download(url, output_dir, max_duration)
