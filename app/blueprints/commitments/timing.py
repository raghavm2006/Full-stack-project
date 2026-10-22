"""Resolve explicit interview context without changing stored user decisions."""
import re
from datetime import datetime, timedelta, timezone
from dateutil import parser
from app.utils.email_text import current_message_text

IST = timezone(timedelta(hours=5, minutes=30))


def commitment_timing(item):
    if item.deadline_at:
        at = item.deadline_at
        if at.tzinfo:
            at = at.astimezone(timezone.utc)
        return {"at": at.replace(tzinfo=None), "kind": "deadline", "note": item.deadline_note}
    body = current_message_text(item.source_email.body or "")
    schedule = re.search(r"interview date(?: and time)?\s*:\s*([^\r\n]+)", body, re.I)
    if not schedule:
        return {"at": None, "kind": "unknown", "note": item.deadline_note}
    raw = schedule[1].replace("*", "").strip()
    date_match = re.search(r"\b\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s*,?\s*\d{4}\b", raw)
    if not date_match:
        return {"at": None, "kind": "unknown", "note": item.deadline_note}
    try:
        day = parser.parse(date_match[0], fuzzy=False).replace(tzinfo=IST)
        times = re.findall(r"\b\d{1,2}(?::\d{2})?\s*(?:AM|PM)\b", raw, re.I)
        start = parser.parse(times[0], default=day) if times else day.replace(hour=0, minute=0)
        end = parser.parse(times[-1], default=day) if times else day + timedelta(days=1)
    except (ValueError, OverflowError):
        return {"at": None, "kind": "unknown", "note": item.deadline_note}
    # Never silently treat an explicitly non-IST schedule as India time.
    if re.search(r"\b(?:UTC|GMT|PST|PDT|EST|EDT|CET)\b|[+-]\d{2}:?\d{2}", raw, re.I):
        return {"at": None, "kind": "unknown", "note": "Schedule timezone needs clarification."}
    prerequisite = re.search(r"(?:at least\s+)?(?:1|one)\s+day\s+prior", body, re.I)
    task = item.description.lower()
    if prerequisite and re.search(r"\b(?:registration|register|resume|résumé|sign.in)\b", task):
        at = start - timedelta(days=1)
        kind = "inferred_deadline"
        note = "Suggested deadline: one day before the interview. Schedule assumed IST; verify in the source email."
        if not times:
            note += " No interview time given; uses the start of that day as a conservative cutoff."
    else:
        at, kind = end, "event_end"
        note = "Related interview has a scheduled end; this is context, not an explicit task deadline. Schedule assumed IST."
    return {"at": at.astimezone(timezone.utc).replace(tzinfo=None), "kind": kind, "note": note}
