"""Timing and interval overlap utilities."""

from typing import List, Tuple, TypeVar


def intervals_overlap(
    a_start: float, a_end: float, b_start: float, b_end: float
) -> bool:
    """Return True if interval [a_start, a_end) overlaps [b_start, b_end)."""
    return a_start < b_end and b_start < a_end


def overlap_duration(
    a_start: float, a_end: float, b_start: float, b_end: float
) -> float:
    """Return the duration of overlap between two intervals."""
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def proportional_char_position(
    event_start: float,
    segment_start: float,
    segment_end: float,
    text_length: int,
) -> int:
    """
    Map a time event position to an approximate character index within text.
    Clamps to [0, text_length].
    """
    seg_duration = max(segment_end - segment_start, 1e-6)
    ratio = (event_start - segment_start) / seg_duration
    ratio = max(0.0, min(1.0, ratio))
    return int(ratio * text_length)
