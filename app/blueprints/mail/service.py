import base64
import json
import mimetypes
import re
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import getaddresses, make_msgid, format_datetime
from datetime import datetime, timezone
from werkzeug.utils import secure_filename

from app.blueprints.nlp_features.insights import message_sentences
from app.blueprints.nlp_features.action_extractor import extract_action_items

MAX_ATTACHMENTS = 10
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024


def addresses(value, required=False):
    if any(c in value for c in "\r\n\x00") or len(value) > 10000:
        raise ValueError("Invalid recipient header")
    try:
        pairs = getaddresses([value])
    except (ValueError, IndexError):
        raise ValueError("Enter valid email addresses separated by commas")
    result = []
    for name, address in pairs:
        if not address and not value.strip():
            continue
        if not re.fullmatch(r"[^\s@<>,;]+@[^\s@<>,;]+\.[^\s@<>,;]+", address):
            raise ValueError("Enter valid email addresses separated by commas")
        if address not in result:
            result.append(address)
    if required and not result:
        raise ValueError("Enter at least one To recipient")
    if len(result) > 50:
        raise ValueError("Maximum 50 recipients per field")
    return ", ".join(result)


def original_headers(email):
    try:
        message = json.loads(email.raw_payload or "{}")
        return {h["name"].lower(): h["value"] for h in message.get("payload", {}).get("headers", [])}
    except (ValueError, TypeError, AttributeError, KeyError):
        return {}


def reply_defaults(email, user):
    headers = original_headers(email)
    target = headers.get("reply-to") or email.sender or ""
    if addresses(target).casefold() == user.email.casefold():
        target = email.receiver or ""
    subject = email.subject or ""
    return {"to": addresses(target), "subject": subject if re.match(r"^re:", subject, re.I) else "Re: " + subject}


def read_attachments(files, existing=()):
    attachments = list(existing)
    used = sum(len(content) for name, mime, content in attachments)
    for file in files:
        if not file.filename:
            continue
        if len(attachments) >= MAX_ATTACHMENTS:
            raise ValueError("Maximum 10 attachments")
        content = file.stream.read(MAX_ATTACHMENT_BYTES - used + 1)
        used += len(content)
        if used > MAX_ATTACHMENT_BYTES:
            raise ValueError("Attachments must total 10 MB or less")
        name = secure_filename(file.filename) or "attachment"
        mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
        attachments.append((name, mime, content))
    return attachments


def build_message(user, fields, attachments, reply=None):
    recipients = addresses(fields.get("to", ""), required=True)
    cc, bcc = addresses(fields.get("cc", "")), addresses(fields.get("bcc", ""))
    subject = fields.get("subject", "").strip()
    body = fields.get("body", "")
    if not subject or len(subject) > 998 or any(c in subject for c in "\r\n\x00"):
        raise ValueError("Enter a valid subject (maximum 998 characters)")
    if not body.strip() or len(body) > 100000:
        raise ValueError("Enter a message of up to 100,000 characters")
    message = EmailMessage(policy=SMTP)
    message["From"] = user.email
    message["To"] = recipients
    if cc:
        message["Cc"] = cc
    if bcc:
        message["Bcc"] = bcc
    message["Subject"] = subject
    message["Date"] = format_datetime(datetime.now(timezone.utc))
    message["Message-ID"] = make_msgid()
    thread_id = None
    if reply:
        headers = original_headers(reply)
        parent = headers.get("message-id", "").strip()
        if not re.fullmatch(r"<[^\s<>]+@[^\s<>]+>", parent):
            raise ValueError("Original Message-ID is unavailable. Use Compose for a new conversation instead.")
        expected = reply_defaults(reply, user)["subject"]
        if subject != expected:
            raise ValueError("Keep the original reply subject to preserve the Gmail conversation")
        refs = re.findall(r"<[^\s<>]+@[^\s<>]+>", headers.get("references", ""))
        refs = list(dict.fromkeys(refs + [parent]))[-20:]
        message["In-Reply-To"] = parent
        message["References"] = " ".join(refs)
        thread_id = reply.thread_id
    message.set_content(body)
    for name, mime, content in attachments:
        maintype, subtype = mime.split("/", 1)
        message.add_attachment(content, maintype=maintype, subtype=subtype, filename=name)
    return {"recipients": recipients, "cc": cc, "bcc": bcc, "subject": subject, "body": body,
            "thread_id": thread_id, "raw_message": base64.urlsafe_b64encode(message.as_bytes()).decode(),
            "attachments": json.dumps([{"name": name, "bytes": len(content)} for name, mime, content in attachments])}


def saved_attachments(outgoing):
    from email import message_from_bytes
    from email.policy import default
    message = message_from_bytes(base64.urlsafe_b64decode(outgoing.raw_message), policy=default)
    return [(part.get_filename() or "attachment", part.get_content_type(), part.get_payload(decode=True) or b"")
            for part in message.iter_attachments()]


def check_reply(email, draft):
    """Conservative lexical hints, not a guarantee that a question is answered."""
    if not email:
        return []
    requests = []
    stopwords = {"please", "could", "would", "can", "you", "your", "the", "and", "that", "this", "with", "for", "from", "have", "will", "send", "provide", "confirm"}
    terms = set(re.findall(r"[a-z]{3,}", draft.lower())) - stopwords
    groups = [({"availability", "available", "schedule", "time"}, {"available", "availability", "monday", "tuesday", "wednesday", "thursday", "friday", "morning", "afternoon"}),
              ({"attend", "attendance", "participate"}, {"attend", "attendance", "participate", "unable", "decline"}),
              ({"accommodation", "accommodations"}, {"accommodation", "accommodations"})]
    for sentence in message_sentences(email):
        if "?" not in sentence and not extract_action_items(sentence):
            continue
        wanted = set(re.findall(r"[a-z]{3,}", sentence.lower())) - stopwords
        topical = [answers for triggers, answers in groups if triggers & wanted]
        overlap = len(wanted & terms)
        addressed = (all(bool(answers & terms) for answers in topical) if topical
                     else overlap >= min(2, max(1, len(wanted))))
        requests.append({"evidence": sentence, "status": "Possibly addressed — verify" if addressed else "Not clearly addressed"})
    return requests[:12]


def record_sent(user, outgoing, result):
    """Keep sent replies locally so follow-up detection can see them immediately."""
    from email import message_from_bytes
    from email.policy import default
    from app.models import Email
    from app.extensions import db
    if Email.query.filter_by(user_id=user.id, gmail_message_id=result["id"]).first():
        return
    sent_at = datetime.now(timezone.utc)
    mime = message_from_bytes(base64.urlsafe_b64decode(outgoing.raw_message), policy=default)
    raw = {"id": result["id"], "threadId": result.get("threadId") or outgoing.thread_id or result["id"],
           "internalDate": str(int(sent_at.timestamp() * 1000)), "labelIds": ["SENT"],
           "payload": {"mimeType": "text/plain", "headers": [{"name": key, "value": str(value)} for key, value in mime.items()],
                       "body": {"data": base64.urlsafe_b64encode(outgoing.body.encode()).decode()}}}
    db.session.add(Email(user_id=user.id, gmail_message_id=result["id"], thread_id=raw["threadId"],
                         sender=user.email, receiver=outgoing.recipients, subject=outgoing.subject,
                         body=outgoing.body, timestamp=sent_at, is_read=True, raw_payload=json.dumps(raw)))
