"""
Feature engineering + heuristic weak-labeling for priority detection.

There is no public dataset labeled HIGH/MEDIUM/LOW for email priority, so
(as planned before Phase 6 started) we derive pseudo-labels from the same
Enron corpus using a transparent, rule-based heuristic on subject/body/
sender — then train a classifier to APPROXIMATE this heuristic from text
+ engineered features. This is weak supervision: it is only as good as
the heuristic, and that must be stated plainly in the project report
rather than presented as ground truth. The heuristic and its weights are
defined here, in one place, specifically so they can be inspected,
justified, and cited.
"""

import re

URGENCY_KEYWORDS = [
    "urgent", "asap", "immediately", "important", "action required",
    "critical", "priority", "time sensitive", "right away", "emergency",
    "please respond", "need this today", "as soon as possible",
]

DEADLINE_PATTERN = re.compile(
    r"\b(by (monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"today|tomorrow|tonight|eod|cob|end of day|close of business|"
    r"\d{1,2}/\d{1,2}(/\d{2,4})?)|due (by|date)|deadline)\b",
    re.IGNORECASE,
)

REPLY_FORWARD_PATTERN = re.compile(r"^(re|fwd?)\s*:", re.IGNORECASE)


def extract_features(subject: str, body: str, sender: str) -> dict:
    subject = subject or ""
    body = body or ""
    sender = sender or ""
    combined = f"{subject} {body}"

    urgency_keyword_count = sum(
        1 for kw in URGENCY_KEYWORDS if kw in combined.lower()
    )
    has_deadline_phrase = bool(DEADLINE_PATTERN.search(combined))
    exclamation_count = combined.count("!")
    question_mark_count = combined.count("?")
    is_reply_or_forward = bool(REPLY_FORWARD_PATTERN.match(subject.strip()))
    subject_is_shouting = subject.isupper() and len(subject.strip()) > 3
    sender_is_internal = "@enron.com" in sender.lower()
    body_length = len(body)

    return {
        "urgency_keyword_count": urgency_keyword_count,
        "has_deadline_phrase": int(has_deadline_phrase),
        "exclamation_count": exclamation_count,
        "question_mark_count": question_mark_count,
        "is_reply_or_forward": int(is_reply_or_forward),
        "subject_is_shouting": int(subject_is_shouting),
        "sender_is_internal": int(sender_is_internal),
        "body_length": body_length,
    }


def heuristic_priority_label(features: dict) -> str:
    """
    Weighted scoring rule -> HIGH / MEDIUM / LOW. Weights were chosen to
    make urgency language and deadlines the dominant signal (the two
    things a human would actually look for), with reply/internal-sender
    as smaller supporting signals. Documented here, not tuned invisibly.
    """
    score = 0
    score += 3 * features["urgency_keyword_count"]
    score += 4 if features["has_deadline_phrase"] else 0
    score += 1 if features["exclamation_count"] > 0 else 0
    score += 1 if features["subject_is_shouting"] else 0
    score += 1 if features["sender_is_internal"] else 0
    score -= 1 if features["is_reply_or_forward"] else 0  # threads trend lower-urgency

    if score >= 5:
        return "HIGH"
    if score >= 2:
        return "MEDIUM"
    return "LOW"
