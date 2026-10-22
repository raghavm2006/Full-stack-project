import hashlib
import re
from datetime import timezone
from email.utils import parseaddr

from app.extensions import db
from app.models import Commitment, Email
from app.blueprints.nlp_features.insights import message_sentences, reference_time
from app.blueprints.nlp_features.deadline_extractor import extract_deadlines

_PROMISE = re.compile(r"\b(?:i|we)\s+(?:will|shall|promise to|commit to)\s+(?:send|submit|deliver|share|finish|complete|review|provide|prepare|confirm|pay|upload|update|respond)\b|\b(?:i'll|we'll)\s+(?:send|submit|deliver|share|finish|complete|review|provide|prepare|confirm|pay|upload|update|respond)\b", re.I)
_REQUEST = re.compile(r"\b(?:please|kindly|(?:can|could|would) you|you (?:must|need to))\s+(?:send|submit|deliver|share|finish|complete|review|provide|prepare|confirm|pay|upload|update|respond)\b", re.I)
_CHANGE = re.compile(r"\b(?:instead|reschedul\w*|deadline (?:has |is )?changed|move (?:it|the deadline)|earlier|later)\b", re.I)
_NEGATED = re.compile(r"\b(?:do not|don't|will not|won't|cannot|can't|no longer|already (?:sent|submitted|completed)|cancelled|canceled)\b", re.I)


def extract_commitments(email, user_email):
    if email.spam_label:
        return []
    own_message = parseaddr(email.sender or "")[1].casefold() == user_email.casefold()
    results = []
    for sentence in message_sentences(email):
        if len(sentence) > 600 or _NEGATED.search(sentence):
            continue
        promise, request = bool(_PROMISE.search(sentence)), bool(_REQUEST.search(sentence))
        change = bool(_CHANGE.search(sentence))
        dates = extract_deadlines(sentence, reference_time(email))
        if not promise and not request and not (change and dates):
            continue
        responsible = ("me" if own_message else "other") if promise else ("other" if own_message else "me")
        deadline = dates[0]["deadline_at"] if dates else None
        if deadline and deadline.tzinfo:
            deadline = deadline.astimezone(timezone.utc).replace(tzinfo=None)
        results.append({"description": sentence, "evidence": sentence,
                        "responsible": responsible, "deadline_at": deadline,
                        "deadline_note": "Confirm extracted date/time; missing times assume 17:00." if dates else "No unambiguous deadline found; set one if needed.",
                        "is_change": change,
                        "fingerprint": hashlib.sha256(sentence.casefold().encode()).hexdigest()})
    return results


def scan_commitments(user):
    existing = {(c.source_email_id, c.fingerprint) for c in Commitment.query.filter_by(user_id=user.id).all()}
    added = 0
    for email in Email.query.filter_by(user_id=user.id).order_by(Email.timestamp, Email.id).all():
        for item in extract_commitments(email, user.email):
            key = (email.id, item["fingerprint"])
            if key in existing:
                continue
            db.session.add(Commitment(user_id=user.id, source_email_id=email.id,
                                      thread_id=email.thread_id, status="proposed", **item))
            existing.add(key)
            added += 1
    db.session.commit()
    return added
