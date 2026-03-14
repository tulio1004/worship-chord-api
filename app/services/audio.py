"""Audio normalization and conversion service using ffmpeg."""

import subprocess
import logging
from pathlib import Path
from dataclasses import dataclass

logger = logging.getLogger(__name__)

TARGET_SAMPLE_RATE = 16000
TARGET_CHANNELS = 1


@dataclass
class AudioInfo:
    path: Path
    sample_rate: int
    channels: int
    duration_seconds: float
    format: str = "wav"


class AudioConversionError(Exception):
    pass


class AudioService:
    """Converts audio files to a clean mono WAV suitable for processing."""

    def normalize(self, input_path: Path, output_dir: Path) -> AudioInfo:
        """
        Convert any audio file to 16kHz mono WAV.
        Returns AudioInfo with the output path.
        """
        output_path = output_dir / "normalized.wav"
        logger.info(f"Normalizing audio: {input_path} -> {output_path}")

        cmd = [
            "ffmpeg",
            "-y",
            "-i", str(input_path),
            "-ac", str(TARGET_CHANNELS),
            "-ar", str(TARGET_SAMPLE_RATE),
            "-sample_fmt", "s16",
            "-vn",   # no video
            str(output_path),
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise AudioConversionError("ffmpeg timed out during conversion")
        except FileNotFoundError:
            raise AudioConversionError(
                "ffmpeg not found. Install ffmpeg and ensure it is in PATH."
            )

        if result.returncode != 0:
            err = result.stderr.strip()[-500:]
            logger.error(f"ffmpeg error: {err}")
            raise AudioConversionError(f"Audio conversion failed: {err}")

        if not output_path.exists() or output_path.stat().st_size == 0:
            raise AudioConversionError("ffmpeg produced an empty output file")

        duration = self._get_duration(output_path)
        logger.info(f"Normalized audio: {duration:.1f}s, {TARGET_SAMPLE_RATE}Hz mono WAV")

        return AudioInfo(
            path=output_path,
            sample_rate=TARGET_SAMPLE_RATE,
            channels=TARGET_CHANNELS,
            duration_seconds=duration,
            format="wav",
        )

    def _get_duration(self, path: Path) -> float:
        """Get audio duration in seconds using ffprobe."""
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15, check=False)
            if result.returncode == 0:
                return float(result.stdout.strip())
        except Exception as e:
            logger.warning(f"Could not get duration via ffprobe: {e}")
        return 0.0
