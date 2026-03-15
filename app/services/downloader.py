"""YouTube audio downloader.

Strategy (tried in order):
  1. InvidiousDownloader — queries a public Invidious API instance to get
     direct YouTube CDN audio URLs, then streams the file down. No cookies or
     JS runtime needed; bypasses Railway IP blocks because the format info is
     resolved by Invidious's server, not ours.
  2. YtDlpDownloader — fallback using yt-dlp (works when the server IP is not
     flagged, e.g. during local development).
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
# Shared types
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
# Strategy 1: Invidious
# ─────────────────────────────────────────────────────────────────────────────

# Public Invidious instances — tried in order, first success wins.
_INVIDIOUS_INSTANCES = [
    "https://inv.nadeko.net",
    "https://invidious.privacydev.net",
    "https://iv.datura.network",
    "https://invidious.flokinet.to",
    "https://yt.artemislena.eu",
    "https://invidious.nerdvpn.de",
]


class InvidiousDownloader:
    """
    Uses the Invidious public API to resolve YouTube audio stream URLs.

    Invidious runs its own YouTube extraction server-side and returns direct
    CDN (googlevideo.com) URLs, which Railway can download without triggering
    YouTube's bot detection.
    """

    def download(
        self,
        url: str,
        output_dir: Path,
        max_duration: int = 600,
    ) -> DownloadResult:
        video_id = _extract_video_id(url)
        logger.info(f"Trying Invidious for video: {video_id}")

        last_error: Exception = YouTubeDownloadError("No Invidious instances tried")

        with httpx.Client(timeout=30, follow_redirects=True) as client:
            for instance in _INVIDIOUS_INSTANCES:
                try:
                    result = self._try_instance(
                        client, instance, video_id, output_dir, max_duration
                    )
                    logger.info(f"Invidious download succeeded via {instance}")
                    return result
                except YouTubeDownloadError:
                    raise  # duration exceeded — don't try other instances
                except Exception as e:
                    logger.warning(f"Invidious instance {instance} failed: {e}")
                    last_error = e

        raise YouTubeDownloadError(
            f"All Invidious instances failed. Last error: {last_error}"
        )

    def _try_instance(
        self,
        client: httpx.Client,
        instance: str,
        video_id: str,
        output_dir: Path,
        max_duration: int,
    ) -> DownloadResult:
        # Fetch video metadata + format list
        resp = client.get(
            f"{instance}/api/v1/videos/{video_id}",
            params={"fields": "title,author,lengthSeconds,adaptiveFormats"},
        )
        resp.raise_for_status()
        data = resp.json()

        duration = int(data.get("lengthSeconds") or 0)
        if duration and duration > max_duration:
            raise YouTubeDownloadError(
                f"Video duration {duration}s exceeds maximum {max_duration}s"
            )

        # Pick best audio-only format
        formats = [
            f for f in data.get("adaptiveFormats", [])
            if f.get("type", "").startswith("audio/")
        ]
        if not formats:
            raise RuntimeError("No audio formats returned by Invidious")

        best = max(formats, key=lambda f: int(f.get("bitrate", 0)))
        audio_url = best["url"]
        ext = "m4a" if "mp4" in best.get("type", "") else "webm"
        output_path = output_dir / f"{video_id}.{ext}"

        logger.info(f"Downloading audio stream ({best.get('bitrate',0)//1000} kbps {ext})")

        # Stream download
        with client.stream("GET", audio_url) as stream:
            stream.raise_for_status()
            with open(output_path, "wb") as f:
                for chunk in stream.iter_bytes(chunk_size=65536):
                    f.write(chunk)

        size_kb = output_path.stat().st_size // 1024
        logger.info(f"Downloaded {size_kb} KB → {output_path.name}")

        return DownloadResult(
            audio_path=output_path,
            title=data.get("title"),
            artist=data.get("author"),
            duration_seconds=float(duration) if duration else None,
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
# Facade: try Invidious, fall back to yt-dlp
# ─────────────────────────────────────────────────────────────────────────────

class YouTubeDownloader:
    """Tries Invidious first, falls back to yt-dlp."""

    def __init__(self):
        self._invidious = InvidiousDownloader()
        self._ytdlp = YtDlpDownloader()

    def download(
        self,
        url: str,
        output_dir: Path,
        max_duration: int = 600,
    ) -> DownloadResult:
        try:
            return self._invidious.download(url, output_dir, max_duration)
        except YouTubeDownloadError:
            raise  # duration exceeded — don't retry
        except Exception as e:
            logger.warning(f"Invidious failed ({e}), falling back to yt-dlp")

        return self._ytdlp.download(url, output_dir, max_duration)
