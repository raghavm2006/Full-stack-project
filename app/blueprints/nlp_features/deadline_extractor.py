"""
Phase 8: deadline detection.

Finds date/time phrases that follow a small set of deadline-signaling
trigger words ("by", "due", "deadline", "before", "no later than",
"until") and turns them into real datetimes. `dateutil.parser` handles
well-formed dates ("March 3rd", "03/15/2026") but has no idea what
"tomorrow", "next Friday", or "EOD" mean, so those relative/informal
phrases are normalized by hand first. Kept as a pure function (no DB,
no Flask) so it's testable with a fixed `reference_time` instead of
depending on "now".
"""

import re
from datetime import datetime, timedelta, timezone

from dateutil import parser as dateutil_parser

_TRIGGER_PATTERN = re.compile(
    r"\b(?:by|due|deadline|before|no later than|until)\b[:\s]+"
    r"([A-Za-z0-9,:+./\- \t]{3,60}?)(?=[.;\n!?]|,(?!\s*\d)|$)",
    re.IGNORECASE,
)

_EOD_PATTERN = re.compile(r"\b(eod|end of day|cob|close of business)\b", re.IGNORECASE)

_WEEKDAYS = [
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
]

_NEXT_WEEKDAY_PATTERN = re.compile(r"^next\s+(\w+)$")


def extract_deadlines(text: str, reference_time: datetime = None) -> list:
    """
    Returns a list of {"description": <matched phrase>, "deadline_at":
    <datetime>} dicts, in the order the phrases appear, deduplicated by
    the resolved datetime. Phrases that don't resolve to a real date
    (parsing failure) are silently skipped rather than raising, since
    this runs over free-form email text that will often not match.
    """
    if not text or not text.strip():
        return []

    reference_time = reference_time or datetime.now(timezone.utc)
    results = []
    seen = set()

    for match in _TRIGGER_PATTERN.finditer(text):
        raw_phrase = match.group(1).strip()
        if not raw_phrase:
            continue

        parsed = _parse_phrase(raw_phrase, reference_time)
        if parsed is None:
            continue

        key = parsed.isoformat()
        if key in seen:
            continue
        seen.add(key)

        results.append({
            "description": match.group(0).strip(),
            "deadline_at": parsed,
        })

    return results


def _default_time(reference_time: datetime) -> datetime:
    """No explicit time mentioned -> assume end of business day (5 PM)."""
    return reference_time.replace(hour=17, minute=0, second=0, microsecond=0)


def _next_weekday(reference_time: datetime, weekday_index: int, force_next_week: bool) -> datetime:
    days_ahead = (weekday_index - reference_time.weekday()) % 7
    if days_ahead == 0 and force_next_week:
        days_ahead = 7
    return reference_time + timedelta(days=days_ahead)


def _parse_phrase(phrase: str, reference_time: datetime):
    normalized = phrase.strip().lower()
    normalized = re.sub(r"^by\s+", "", normalized)
    normalized = re.sub(r"\s+instead$", "", normalized)
    numeric_date = re.search(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-]\d{2,4})?\b", normalized)
    if numeric_date and int(numeric_date[1]) <= 12 and int(numeric_date[2]) <= 12:
        return None  # Locale-dependent date: show it for human clarification.
    in_days = re.fullmatch(r"in (\d{1,3}) days?", normalized)
    if in_days:
        return _default_time(reference_time + timedelta(days=int(in_days[1])))
    weekday_time = re.fullmatch(r"(?:(next|this)\s+)?(" + "|".join(_WEEKDAYS) + r")(?:\s+(?:at\s+)?(.+))?", normalized)
    if weekday_time:
        base = _next_weekday(reference_time, _WEEKDAYS.index(weekday_time[2]), weekday_time[1] == "next")
        if not weekday_time[3]:
            return _default_time(base)
        try:
            return dateutil_parser.parse(weekday_time[3], default=_default_time(base))
        except (ValueError, OverflowError):
            return None

    relative = re.match(r"^(today|tomorrow)(?:\s+(?:at\s+)?(.+))?$", normalized)
    if relative:
        base = reference_time + timedelta(days=relative.group(1) == "tomorrow")
        time_phrase = relative.group(2)
        if not time_phrase or _EOD_PATTERN.search(time_phrase):
            return _default_time(base)
        try:
            return dateutil_parser.parse(time_phrase, default=_default_time(base))
        except (ValueError, OverflowError):
            return None

    if _EOD_PATTERN.search(normalized):
        if "tomorrow" in normalized:
            return _default_time(reference_time + timedelta(days=1))
        return _default_time(reference_time)

    if normalized == "today":
        return _default_time(reference_time)

    if normalized == "tomorrow":
        return _default_time(reference_time + timedelta(days=1))

    next_match = _NEXT_WEEKDAY_PATTERN.match(normalized)
    if next_match and next_match.group(1) in _WEEKDAYS:
        weekday_index = _WEEKDAYS.index(next_match.group(1))
        return _default_time(_next_weekday(reference_time, weekday_index, force_next_week=True))

    if normalized in _WEEKDAYS:
        weekday_index = _WEEKDAYS.index(normalized)
        return _default_time(_next_weekday(reference_time, weekday_index, force_next_week=False))

    try:
        parsed = dateutil_parser.parse(phrase, fuzzy=True, default=_default_time(reference_time))
    except (ValueError, OverflowError):
        return None

    if parsed.tzinfo is None and reference_time.tzinfo is not None:
        parsed = parsed.replace(tzinfo=reference_time.tzinfo)

    return parsed
