"""
Phase 8: action-item extraction.

Rule-based on purpose: emails asking for something ("please send the
report", "can you review this", "you need to sign the attached form")
follow a small set of recognizable request patterns. A rule-based
extractor is transparent (easy to explain in a project report), needs
no labeled training data, and runs instantly — trading some recall for
being independently testable and debuggable line-by-line.
"""

import re

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|[\r\n]+")

_REQUEST_PATTERNS = [
    re.compile(r"\bplease\b", re.IGNORECASE),
    re.compile(r"\bkindly\b", re.IGNORECASE),
    re.compile(r"\b(can|could|would) you\b", re.IGNORECASE),
    re.compile(r"\bneeds?\s+to\b", re.IGNORECASE),
    re.compile(r"\brequired?\s+to\b", re.IGNORECASE),
    re.compile(r"\bdon'?t forget to\b", re.IGNORECASE),
    re.compile(r"\bmake sure (to|you)\b", re.IGNORECASE),
    re.compile(r"\baction (item|required)\b", re.IGNORECASE),
    re.compile(r"\breminder to\b", re.IGNORECASE),
    re.compile(r"\bmust\s+\w+\b", re.IGNORECASE),
]

# Sentences that *open* with one of these (imperative mood) read as a
# direct instruction even without an explicit "please"/"can you".
_IMPERATIVE_OPENERS = {
    "send", "review", "complete", "submit", "prepare", "schedule",
    "confirm", "update", "provide", "attach", "sign", "approve",
    "finalize", "respond", "reply", "call", "join", "forward", "upload",
    "share", "fix", "check", "verify", "follow-up", "followup",
}

_MAX_SENTENCE_LENGTH = 240  # skip long paragraphs — unlikely to be one clean action item


def extract_action_items(text: str, max_items: int = 5) -> list:
    """
    Returns up to `max_items` sentences from `text` that read as
    actionable requests, in the order they appear, with exact duplicates
    removed (case-insensitive).
    """
    if not text or not text.strip() or max_items <= 0:
        return []

    sentences = [s.strip() for s in _SENTENCE_SPLIT.split(text) if s.strip()]
    matches = []
    seen = set()

    for sentence in sentences:
        # A prohibition is useful context, but not a task to perform.
        if re.search(r"\b(?:do not|don't|must not|cannot|can't|no longer (?:need|required))\b", sentence, re.I):
            continue
        if re.search(r"\b(?:already (?:sent|submitted|completed|reviewed)|(?:task|request) (?:is |was )?(?:completed|cancelled|canceled))\b", sentence, re.I):
            continue
        if len(sentence) > _MAX_SENTENCE_LENGTH:
            continue

        is_match = any(pattern.search(sentence) for pattern in _REQUEST_PATTERNS)

        if not is_match:
            first_word = re.split(r"\s", sentence, maxsplit=1)[0].lower().strip(",:;\"'")
            is_match = first_word in _IMPERATIVE_OPENERS

        if not is_match:
            continue

        key = sentence.lower()
        if key in seen:
            continue
        seen.add(key)
        matches.append(sentence)

        if len(matches) >= max_items:
            break

    return matches
