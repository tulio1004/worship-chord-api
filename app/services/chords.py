"""
Chord extraction service.

Engines (in preference order):
  1. ChordinoEngine  — Chordino VAMP plugin via chord-extractor library.
                       Significantly more accurate than chromagram matching.
                       Works on Linux (Railway). Auto-detected; falls back on failure.
  2. LibrosaChordEngine — CQT chromagram template matching.
                          Pure Python, works everywhere. Used as fallback.

The factory `create_chord_service` tries Chordino when engine="auto" or "chordino",
and silently falls back to librosa if the import or VAMP plugin is unavailable.
"""

import logging
import numpy as np
from pathlib import Path
from typing import List, Protocol, runtime_checkable
from dataclasses import dataclass

from app.utils.chord_utils import normalize_chord_label

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Data types
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ChordEvent:
    start: float
    end: float
    raw_label: str
    label: str
    confidence: float | None = None


@runtime_checkable
class ChordExtractionEngine(Protocol):
    def extract(self, audio_path: Path, prefer_sharps: bool = True) -> List[ChordEvent]: ...

    @property
    def engine_name(self) -> str: ...


# ─────────────────────────────────────────────────────────────────────────────
# Engine 1: Chordino (via chord-extractor library)
# ─────────────────────────────────────────────────────────────────────────────

class ChordinoEngine:
    """
    Uses the Chordino VAMP plugin for chord extraction via the chord-extractor library.

    On Linux (Railway), the library auto-configures VAMP_PATH to its bundled
    nnls-chroma.so plugin. This engine is significantly more accurate than the
    librosa chromagram approach.

    On Windows, this engine will fail to import (no .so) and fall back to librosa.
    """

    @property
    def engine_name(self) -> str:
        return "chordino"

    def _load(self):
        """Verify that chord-extractor and vamp are importable."""
        from chord_extractor.extractors import Chordino  # noqa: F401

    def extract(self, audio_path: Path, prefer_sharps: bool = True) -> List[ChordEvent]:
        from chord_extractor.extractors import Chordino

        logger.info(f"Extracting chords with Chordino from: {audio_path.name}")
        extractor = Chordino(roll_on=1)
        raw = extractor.extract(str(audio_path))

        events: List[ChordEvent] = []
        for i, change in enumerate(raw):
            chord = change.chord
            if chord in ("N", "N/A", "", None):
                continue
            start = float(change.timestamp)
            end = float(raw[i + 1].timestamp) if i + 1 < len(raw) else start + 4.0
            if end - start < 0.3:
                continue
            label = normalize_chord_label(chord, prefer_sharps=prefer_sharps)
            events.append(ChordEvent(
                start=round(start, 3),
                end=round(end, 3),
                raw_label=chord,
                label=label,
            ))

        logger.info(f"Chordino detected {len(events)} chord events")
        return events


# ─────────────────────────────────────────────────────────────────────────────
# Engine 2: Librosa chromagram (pure Python fallback)
# ─────────────────────────────────────────────────────────────────────────────

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def _build_chord_templates() -> dict[str, np.ndarray]:
    templates: dict[str, np.ndarray] = {}
    for i, note in enumerate(NOTE_NAMES):
        maj = np.zeros(12)
        maj[i % 12] = 1.0
        maj[(i + 4) % 12] = 1.0
        maj[(i + 7) % 12] = 1.0
        templates[note] = maj / maj.sum()

        min_ = np.zeros(12)
        min_[i % 12] = 1.0
        min_[(i + 3) % 12] = 1.0
        min_[(i + 7) % 12] = 1.0
        templates[f"{note}m"] = min_ / min_.sum()
    return templates


CHORD_TEMPLATES = _build_chord_templates()


def _match_chord(chroma_vec: np.ndarray) -> tuple[str, float]:
    energy = float(chroma_vec.sum())
    if energy < 0.01:
        return "N", 0.0
    normed = chroma_vec / (energy + 1e-8)
    best_label, best_score = "N", -1.0
    for label, template in CHORD_TEMPLATES.items():
        score = float(np.dot(normed, template))
        if score > best_score:
            best_score = score
            best_label = label
    return best_label, best_score


def _smooth_sequence(seq: list, window: int = 7) -> list:
    if len(seq) <= window:
        return seq
    result = []
    half = window // 2
    for i in range(len(seq)):
        start = max(0, i - half)
        end = min(len(seq), i + half + 1)
        window_vals = seq[start:end]
        result.append(max(set(window_vals), key=window_vals.count))
    return result


def _to_segments(labels: list[str], times: np.ndarray) -> list[tuple[float, float, str]]:
    if not labels:
        return []
    segments = []
    current_label = labels[0]
    current_start = float(times[0])
    for i in range(1, len(labels)):
        if labels[i] != current_label:
            segments.append((current_start, float(times[i]), current_label))
            current_label = labels[i]
            current_start = float(times[i])
    if len(times) > 0:
        segments.append((current_start, float(times[-1]), current_label))
    return segments


class LibrosaChordEngine:
    """CQT chromagram chord detection — pure Python, works everywhere."""

    def __init__(self, hop_length: int = 4096, sr: int = 22050, smooth_window: int = 9):
        self.hop_length = hop_length
        self.sr = sr
        self.smooth_window = smooth_window

    @property
    def engine_name(self) -> str:
        return "librosa"

    def extract(self, audio_path: Path, prefer_sharps: bool = True) -> List[ChordEvent]:
        import librosa

        logger.info(f"Extracting chords with librosa from: {audio_path.name}")
        y, sr = librosa.load(str(audio_path), sr=self.sr, mono=True)
        if len(y) == 0:
            raise ValueError("Audio file is empty or could not be loaded")

        chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=self.hop_length)
        times = librosa.frames_to_time(
            np.arange(chroma.shape[1]), sr=sr, hop_length=self.hop_length
        )

        raw_labels = [_match_chord(chroma[:, i])[0] for i in range(chroma.shape[1])]
        smoothed = _smooth_sequence(raw_labels, window=self.smooth_window)
        segments = _to_segments(smoothed, times)

        events: List[ChordEvent] = []
        for start, end, raw in segments:
            if end - start < 0.5:
                continue
            clean = normalize_chord_label(raw, prefer_sharps=prefer_sharps)
            events.append(ChordEvent(
                start=round(start, 3),
                end=round(end, 3),
                raw_label=raw,
                label=clean,
            ))

        logger.info(f"Librosa detected {len(events)} chord events")
        return events


# ─────────────────────────────────────────────────────────────────────────────
# Facade + factory
# ─────────────────────────────────────────────────────────────────────────────

class ChordService:
    def __init__(self, engine: ChordExtractionEngine):
        self._engine = engine

    @property
    def engine_name(self) -> str:
        return self._engine.engine_name

    def extract(self, audio_path: Path, prefer_sharps: bool = True) -> List[ChordEvent]:
        return self._engine.extract(audio_path, prefer_sharps=prefer_sharps)


def create_chord_service(engine_name: str = "auto") -> ChordService:
    """
    Factory for chord services.

    engine_name="auto"     → try Chordino, fall back to librosa
    engine_name="chordino" → require Chordino (raises if unavailable)
    engine_name="librosa"  → always use librosa
    """
    if engine_name == "librosa":
        return ChordService(LibrosaChordEngine())

    if engine_name in ("chordino", "auto"):
        try:
            engine = ChordinoEngine()
            engine._load()  # verify the import works now
            logger.info("Chordino engine available — using it")
            return ChordService(engine)
        except Exception as e:
            if engine_name == "chordino":
                raise RuntimeError(f"Chordino engine requested but not available: {e}")
            logger.info(f"Chordino not available ({e}), falling back to librosa")
            return ChordService(LibrosaChordEngine())

    raise ValueError(f"Unknown chord engine: {engine_name!r}")
