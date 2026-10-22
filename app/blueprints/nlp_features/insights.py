"""Evidence-based key information; no external API or mutation of old tasks."""
import json
import re
from email.utils import parsedate_to_datetime
from app.utils.email_text import current_message_text
from app.blueprints.emails.parser import clean_template_comments
from app.blueprints.nlp_features.action_extractor import extract_action_items
from app.blueprints.nlp_features.deadline_extractor import extract_deadlines
from app.blueprints.nlp_features.summarizer import summarize_text


def reference_time(email):
    try:
        payload = json.loads(email.raw_payload or "{}")
        for header in payload.get("payload", {}).get("headers", []):
            if header.get("name", "").lower() == "date":
                value = parsedate_to_datetime(header["value"])
                if value.tzinfo:
                    return value
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        pass
    return email.timestamp


def message_sentences(email):
    text = clean_template_comments(current_message_text(email.body))
    return [" ".join(s.split()) for s in re.split(r"(?<=[.!?])\s+|[\r\n]+", text) if s.strip()]


def key_information(email):
    sentences = message_sentences(email)
    actions, deadlines, restrictions = [], [], []
    for sentence in sentences:
        if extract_action_items(sentence):
            actions.append(sentence)
        if re.search(r"\b(?:do not|don't|must not|cannot|can't|never)\b", sentence, re.I):
            restrictions.append(sentence)
        found = extract_deadlines(sentence, reference_time(email))
        for deadline in found:
            deadlines.append({**deadline, "evidence": sentence, "needs_confirmation": True})
        if not found and re.search(r"\b(?:due|deadline|no later than|by (?:next|this|the end|\d+))\b", sentence, re.I):
            deadlines.append({"description": "Date needs clarification", "deadline_at": None,
                              "evidence": sentence, "needs_confirmation": True})
    return {"overview": summarize_text("\n".join(sentences), max_sentences=2, max_chars=450),
            "actions": list(dict.fromkeys(actions))[:5], "deadlines": deadlines[:5],
            "restrictions": list(dict.fromkeys(restrictions))[:3]}
