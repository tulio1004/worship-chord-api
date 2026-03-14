import pytest
from app.utils.chord_utils import normalize_chord_label, is_no_chord, chords_to_display


@pytest.mark.parametrize("raw,prefer_sharps,expected", [
    ("C:maj", True, "C"),
    ("A:min", True, "Am"),
    ("G#:maj", True, "G#"),
    ("Bb:min", True, "A#m"),
    ("Bb:min", False, "Bbm"),
    ("D#:maj7", True, "D#maj7"),
    ("N", True, "N.C."),
    ("N.C.", True, "N.C."),
    ("G", True, "G"),
    ("Am", True, "Am"),
    ("C#m", True, "C#m"),
    ("Db:maj", True, "C#"),
    ("F#:min", False, "Gbm"),
])
def test_normalize_chord_label(raw, prefer_sharps, expected):
    result = normalize_chord_label(raw, prefer_sharps=prefer_sharps)
    assert result == expected, f"normalize_chord_label({raw!r}, prefer_sharps={prefer_sharps}) = {result!r}, expected {expected!r}"


def test_is_no_chord_true():
    assert is_no_chord("N.C.")
    assert is_no_chord("N")
    assert is_no_chord("NC")


def test_is_no_chord_false():
    assert not is_no_chord("G")
    assert not is_no_chord("Am")


def test_chords_to_display():
    assert chords_to_display("G") == "[G]"
    assert chords_to_display("Am7") == "[Am7]"
