import pytest
from app.services.alignment import align, _build_display_line, ActiveChordHint
from app.services.chords import ChordEvent
from app.services.transcription import TranscriptionSegment


def _chord(start, end, label):
    return ChordEvent(start=start, end=end, raw_label=label, label=label)


def _seg(start, end, text):
    return TranscriptionSegment(start=start, end=end, text=text)


def test_align_basic():
    chords = [
        _chord(0.0, 5.0, "G"),
        _chord(5.0, 10.0, "C"),
    ]
    segments = [
        _seg(0.0, 5.0, "Amazing grace how sweet the sound"),
        _seg(5.0, 10.0, "That saved a wretch like me"),
    ]
    blocks = align(chords, segments)
    assert len(blocks) == 2
    assert blocks[0].active_chords[0].label == "G"
    assert blocks[1].active_chords[0].label == "C"


def test_align_chord_within_segment():
    chords = [
        _chord(0.0, 2.0, "G"),
        _chord(2.0, 4.0, "C"),
        _chord(4.0, 6.0, "G"),
    ]
    segments = [_seg(0.0, 6.0, "Amazing grace how sweet the sound")]
    blocks = align(chords, segments)
    assert len(blocks) == 1
    labels = [h.label for h in blocks[0].active_chords]
    assert "G" in labels
    assert "C" in labels


def test_display_line_with_chords():
    hints = [
        ActiveChordHint(position_hint=0, label="G"),
        ActiveChordHint(position_hint=15, label="C"),
    ]
    lyric = "Amazing grace how sweet the sound"
    result = _build_display_line(lyric, hints)
    assert "[G]" in result
    assert "[C]" in result


def test_align_empty_chords():
    segments = [_seg(0.0, 4.0, "Amazing grace")]
    blocks = align([], segments)
    assert len(blocks) == 1
    assert blocks[0].active_chords == []
    assert blocks[0].display_line == "Amazing grace"


def test_align_empty_segments():
    chords = [_chord(0.0, 4.0, "G")]
    blocks = align(chords, [])
    assert blocks == []
