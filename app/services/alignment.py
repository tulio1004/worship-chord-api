"""
Chord-lyric alignment service.

Strategy: timestamp_overlap_v1
- For each lyric segment, identify which chord is active at its start,
  and which chords change during its duration
- Only one chord can occupy position 0 (the most recently active chord)
- Within-segment chord changes are mapped proportionally to character positions
- Minimum spacing between chord markers is enforced to avoid clustering
"""

import logging
from typing import List, Optional
from dataclasses import dataclass

from app.services.chords import ChordEvent
from app.services.transcription import TranscriptionSegment
from app.utils.chord_utils import is_no_chord, chords_to_display
from app.utils.timing_utils import intervals_overlap, proportional_char_position

logger = logging.getLogger(__name__)

ALIGNMENT_METHOD = "timestamp_overlap_v1"
MIN_CHAR_GAP = 8  # minimum characters between consecutive chord markers


@dataclass
class ActiveChordHint:
    position_hint: int
    label: str


@dataclass
class AlignmentBlock:
    start: float
    end: float
    lyric: str
    active_chords: List[ActiveChordHint]
    display_line: str


def _snap_to_word_start(text: str, pos: int) -> int:
    """
    Move pos backward to the start of the current word.
    If pos is mid-word, find the preceding space and step past it.
    """
    if pos <= 0:
        return 0
    i = min(pos, len(text) - 1)
    while i > 0 and text[i - 1] not in (" ", "\t"):
        i -= 1
    return i


def _enforce_spacing(hints: List[ActiveChordHint], min_gap: int = MIN_CHAR_GAP) -> List[ActiveChordHint]:
    """
    Drop chord hints that are too close to the previous one.
    If a chord is within min_gap chars of the prior marker and has the same label,
    always drop it. If it has a different label but is too close, also drop it
    (the alignment is approximate anyway).
    """
    if not hints:
        return hints
    result = [hints[0]]
    for h in hints[1:]:
        prev = result[-1]
        if h.label == prev.label:
            continue  # always drop consecutive duplicates
        if h.position_hint - prev.position_hint < min_gap:
            continue  # too close — skip
        result.append(h)
    return result


def _build_display_line(lyric: str, active_chords: List[ActiveChordHint]) -> str:
    """
    Insert chord markers into lyric text at estimated character positions.
    Example: [G]Amazing grace [C]how sweet the [G]sound
    """
    if not active_chords:
        return lyric

    sorted_chords = sorted(active_chords, key=lambda c: c.position_hint)
    result = []
    prev_pos = 0
    text_len = len(lyric)

    for hint in sorted_chords:
        pos = min(hint.position_hint, text_len)
        pos = max(prev_pos, pos)
        result.append(lyric[prev_pos:pos])
        result.append(chords_to_display(hint.label))
        prev_pos = pos

    result.append(lyric[prev_pos:])
    return "".join(result)


def align(
    chord_events: List[ChordEvent],
    segments: List[TranscriptionSegment],
) -> List[AlignmentBlock]:
    """
    Align chord events to lyric segments using timestamp overlap.

    For each segment:
    - Find the chord that is active at the segment's start time
      (the most recent chord event that began before seg_start).
      This goes at position 0.
    - Find chord events that START during the segment and map them
      to proportional character positions.
    - Enforce minimum spacing so markers don't cluster.
    """
    blocks: List[AlignmentBlock] = []

    for seg in segments:
        lyric = seg.text.strip()
        if not lyric:
            continue

        seg_start = seg.start
        seg_end = seg.end
        text_len = len(lyric)

        # ── Chord active at segment start (started before or at seg_start) ──
        # Among all chords overlapping this segment that began before seg_start,
        # keep only the most recently started one.
        pre_chord: Optional[ChordEvent] = None
        for c in chord_events:
            if is_no_chord(c.label):
                continue
            if c.start >= seg_start:
                continue
            if c.end <= seg_start:
                continue  # already ended before segment
            if pre_chord is None or c.start > pre_chord.start:
                pre_chord = c

        # ── Chord changes that happen DURING this segment ──
        within: List[ChordEvent] = [
            c for c in chord_events
            if not is_no_chord(c.label)
            and c.start >= seg_start
            and c.start < seg_end
        ]
        within.sort(key=lambda c: c.start)

        # ── Build hints ──
        hints: List[ActiveChordHint] = []

        if pre_chord:
            hints.append(ActiveChordHint(position_hint=0, label=pre_chord.label))

        for c in within:
            raw_pos = proportional_char_position(c.start, seg_start, seg_end, text_len)
            snapped = _snap_to_word_start(lyric, raw_pos)
            # If this is the very first chord and nothing pre-segment, allow pos 0
            if hints and snapped == 0:
                snapped = 0  # will be filtered by spacing if duplicate
            hints.append(ActiveChordHint(position_hint=snapped, label=c.label))

        hints = _enforce_spacing(hints, min_gap=MIN_CHAR_GAP)

        display = _build_display_line(lyric, hints)

        blocks.append(AlignmentBlock(
            start=round(seg_start, 3),
            end=round(seg_end, 3),
            lyric=lyric,
            active_chords=hints,
            display_line=display,
        ))

    logger.info(f"Aligned {len(blocks)} lyric blocks with chords")
    return blocks
