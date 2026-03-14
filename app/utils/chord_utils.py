"""
Chord label normalization utilities.
Converts raw chord labels from various extraction engines into
clean, guitar-friendly notation.
"""

import re
from typing import Optional

# Maps flat roots to sharp equivalents
FLAT_TO_SHARP: dict[str, str] = {
    "Db": "C#",
    "Eb": "D#",
    "Fb": "E",
    "Gb": "F#",
    "Ab": "G#",
    "Bb": "A#",
    "Cb": "B",
}

# Maps sharp roots to flat equivalents
SHARP_TO_FLAT: dict[str, str] = {v: k for k, v in FLAT_TO_SHARP.items()}
SHARP_TO_FLAT.update({"E": "Fb", "B": "Cb"})  # edge cases omitted in practice

# Quality normalization: maps common raw quality strings to clean suffix
QUALITY_MAP: dict[str, str] = {
    "maj": "",
    "major": "",
    "M": "",
    "": "",
    "min": "m",
    "minor": "m",
    "m": "m",
    "dim": "dim",
    "diminished": "dim",
    "aug": "aug",
    "augmented": "aug",
    "7": "7",
    "dom7": "7",
    "dominant7": "7",
    "maj7": "maj7",
    "major7": "maj7",
    "min7": "m7",
    "minor7": "m7",
    "m7": "m7",
    "sus2": "sus2",
    "sus4": "sus4",
    "sus": "sus4",
    "add9": "add9",
    "6": "6",
    "dim7": "dim7",
    "hdim7": "m7b5",
    "minmaj7": "mMaj7",
}

NO_CHORD_LABELS = {"N", "N.C.", "NC", "X", "None", "none", "n", "n/a"}


def parse_root_and_quality(raw: str) -> tuple[str, str]:
    """
    Parse a raw chord label into (root, quality_suffix).
    Handles formats like:
      C:maj, Am, G#:min, Bbm, D#:maj7, N
    """
    raw = raw.strip()

    if raw in NO_CHORD_LABELS:
        return ("N.C.", "")

    # Handle colon-separated format (from Chordino/autochord/etc.)
    if ":" in raw:
        parts = raw.split(":", 1)
        root = parts[0].strip()
        quality_raw = parts[1].strip()
        quality = QUALITY_MAP.get(quality_raw, quality_raw.lower())
        return (root, quality)

    # Try to extract root note + remainder
    # Root is 1-2 chars: letter + optional # or b
    match = re.match(r"^([A-G][#b]?)(.*)", raw)
    if match:
        root = match.group(1)
        remainder = match.group(2).strip()
        quality = QUALITY_MAP.get(remainder, remainder)
        return (root, quality)

    return (raw, "")


def normalize_root(root: str, prefer_sharps: bool = True) -> str:
    """Convert root note to preferred enharmonic equivalent."""
    if prefer_sharps:
        return FLAT_TO_SHARP.get(root, root)
    else:
        # Only convert the common sharps musicians avoid
        common_flat_prefer = {"C#": "Db", "F#": "Gb", "G#": "Ab", "A#": "Bb", "D#": "Eb"}
        return common_flat_prefer.get(root, root)


def normalize_chord_label(raw: str, prefer_sharps: bool = True) -> str:
    """
    Normalize a raw chord label to clean guitar notation.

    Examples:
      C:maj        -> C
      A:min        -> Am
      G#:maj       -> G# (or Ab if prefer_sharps=False)
      Bb:min       -> Bbm (or A#m if prefer_sharps=True)
      D#:maj7      -> D#maj7
      N            -> N.C.
    """
    if raw.strip() in NO_CHORD_LABELS:
        return "N.C."

    root, quality = parse_root_and_quality(raw)

    if root == "N.C.":
        return "N.C."

    normalized_root = normalize_root(root, prefer_sharps)
    return f"{normalized_root}{quality}"


def chords_to_display(chord_label: str) -> str:
    """Wrap a chord label in brackets: G -> [G]"""
    return f"[{chord_label}]"


def is_no_chord(label: str) -> bool:
    return label in ("N.C.", "N", "NC") or label.strip() == ""
