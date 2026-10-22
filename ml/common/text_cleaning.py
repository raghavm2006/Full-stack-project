"""
Shared parsing/cleaning helpers used by all three ML pipelines
(categorization, spam_detection, priority_detection). Kept separate from
app/blueprints/emails/parser.py deliberately: that module decodes Gmail
API JSON responses; this one decodes raw RFC822 email files straight off
disk (Enron .txt files, SpamAssassin corpus files) using Python's
standard `email` library. Two different input shapes, so two parsers —
sharing code between them would mean one fake abstraction pretending
Gmail's JSON and a raw .eml file are the same thing.
"""

import email
import re
from email import policy


def parse_raw_email_file(path: str) -> dict:
    """
    Reads one raw email file (Enron .txt or a SpamAssassin corpus file)
    and returns {"subject", "sender", "body"}. Tolerant of the encoding
    oddities real-world email corpora are full of — malformed headers,
    non-UTF8 bytes, missing parts — since a single bad file must never
    crash a preprocessing run over thousands of them.
    """
    with open(path, "rb") as f:
        raw_bytes = f.read()

    try:
        message = email.message_from_bytes(raw_bytes, policy=policy.compat32)
    except Exception:
        # Some corpus files are malformed enough that even compat32
        # chokes; fall back to treating the whole thing as a body with
        # no headers rather than dropping the file entirely.
        return {"subject": "", "sender": "", "body": raw_bytes.decode("utf-8", errors="replace")}

    subject = _decode_header_value(message.get("Subject", ""))
    sender = _decode_header_value(message.get("From", ""))
    body = _extract_body(message)

    return {"subject": subject, "sender": sender, "body": body}


def _decode_header_value(value) -> str:
    if value is None:
        return ""
    try:
        return str(value)
    except Exception:
        return ""


def _extract_body(message) -> str:
    """Walks a possibly-multipart message and returns the best plain-text body."""
    if message.is_multipart():
        plain_chunks, html_chunks = [], []
        for part in message.walk():
            if part.is_multipart():
                continue
            content_type = part.get_content_type()
            if content_type not in ("text/plain", "text/html"):
                continue  # skip attachments/images/etc.
            text = _decode_part(part)
            if content_type == "text/plain":
                plain_chunks.append(text)
            else:
                html_chunks.append(text)

        if plain_chunks:
            return "\n".join(plain_chunks)
        if html_chunks:
            return strip_html("\n".join(html_chunks))
        return ""

    content_type = message.get_content_type()
    text = _decode_part(message)
    return strip_html(text) if content_type == "text/html" else text


def _decode_part(part) -> str:
    try:
        payload = part.get_payload(decode=True)
    except Exception:
        payload = None

    if payload is None:
        # get_payload(decode=True) returns None when the part has no
        # transfer-encoding to decode (already plain text).
        raw = part.get_payload()
        return raw if isinstance(raw, str) else ""

    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except LookupError:
        return payload.decode("utf-8", errors="replace")


_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"[ \t]+")
_BLANK_LINES_RE = re.compile(r"\n\s*\n+")


def strip_html(html: str) -> str:
    """Quick, good-enough HTML->text for ML preprocessing (not a real renderer)."""
    text = _TAG_RE.sub(" ", html)
    text = _WHITESPACE_RE.sub(" ", text)
    text = _BLANK_LINES_RE.sub("\n", text)
    return text.strip()


_URL_RE = re.compile(r"https?://\S+|www\.\S+")
_MULTI_WHITESPACE_RE = re.compile(r"\s+")


def clean_for_vectorizer(text: str) -> str:
    """
    Light normalization before TF-IDF: lowercase, strip URLs (they inflate
    vocabulary with one-off tokens and carry little categorical signal),
    collapse whitespace. Deliberately NOT stripping punctuation/numbers —
    TfidfVectorizer's default tokenizer already handles that, and some of
    it (e.g. "$", "%") is genuine signal for Finance-style content.
    """
    text = text.lower()
    text = _URL_RE.sub(" ", text)
    text = _MULTI_WHITESPACE_RE.sub(" ", text)
    return text.strip()
