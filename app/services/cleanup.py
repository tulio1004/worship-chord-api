"""
Lyric cleanup service.
Conservative rule-based cleanup for ASR output.
Does NOT rewrite artistically — only fixes obvious junk.
"""

import re
import logging
from typing import List

logger = logging.getLogger(__name__)

# Patterns that indicate ASR artifacts to remove or fix
_FILLER_WORDS = re.compile(
    r"\b(um+|uh+|hmm+|er+|ah+)\b",
    re.IGNORECASE,
)
_REPEATED_WORD = re.compile(r"\b(\w+)(\s+\1){2,}\b", re.IGNORECASE)
_MULTIPLE_SPACES = re.compile(r"  +")
_TRAILING_PUNCT = re.compile(r"[,;]+$")


def clean_segment_text(text: str) -> str:
    """Apply conservative cleanup to a single segment/line."""
    # Remove filler words
    text = _FILLER_WORDS.sub("", text)
    # Remove triple+ repeated words (ASR stutter)
    text = _REPEATED_WORD.sub(r"\1", text)
    # Collapse multiple spaces
    text = _MULTIPLE_SPACES.sub(" ", text)
    # Strip trailing commas/semicolons that ASR sometimes adds
    text = _TRAILING_PUNCT.sub("", text.rstrip())
    return text.strip()


def split_into_lyric_lines(text: str, max_line_length: int = 60) -> List[str]:
    """
    Split a transcription text into worship-song-appropriate lines.
    Prefers splitting at punctuation, then at natural length boundaries.
    """
    # Split on existing line breaks first
    raw_lines = [line.strip() for line in text.splitlines() if line.strip()]

    if not raw_lines:
        return []

    result: List[str] = []
    for line in raw_lines:
        if len(line) <= max_line_length:
            result.append(line)
        else:
            # Try to split at punctuation
            parts = re.split(r"(?<=[.!?,])\s+", line)
            if len(parts) > 1:
                result.extend(p.strip() for p in parts if p.strip())
            else:
                # Split at word boundary near max_line_length
                words = line.split()
                current = []
                current_len = 0
                for word in words:
                    if current_len + len(word) + 1 > max_line_length and current:
                        result.append(" ".join(current))
                        current = [word]
                        current_len = len(word)
                    else:
                        current.append(word)
                        current_len += len(word) + 1
                if current:
                    result.append(" ".join(current))

    return result


class LyricCleanupService:
    def clean(self, raw_text: str, apply_cleanup: bool = True) -> str:
        """
        Return a cleaned version of the transcription text.
        If apply_cleanup=False, return the text with only whitespace normalization.
        """
        if not apply_cleanup:
            return " ".join(raw_text.split())

        lines = raw_text.splitlines()
        if not lines:
            lines = [raw_text]

        cleaned_lines = [clean_segment_text(line) for line in lines]
        cleaned_lines = [l for l in cleaned_lines if l]

        # Re-split long lines
        final_lines: List[str] = []
        for line in cleaned_lines:
            final_lines.extend(split_into_lyric_lines(line))

        cleaned = "\n".join(final_lines)
        logger.debug(f"Lyric cleanup: {len(raw_text)} -> {len(cleaned)} chars")
        return cleaned
