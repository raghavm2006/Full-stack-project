"""
Phase 4: decodes the raw Gmail API message resource (stored in
Email.raw_payload during Phase 3 sync) into a clean plain-text body.

Gmail already parses out From/To/Subject/date for us (used directly in
Phase 3's sync_service.extract_basic_fields) — the genuinely hard part
this module handles is the MIME body itself: it may be split across
multipart/alternative and multipart/mixed parts, each base64url-encoded,
and the only "plain" text available is sometimes just an HTML part that
has to be stripped down to readable text.
"""

import base64
import re
from html import unescape
from html.parser import HTMLParser


def clean_template_comments(text: str) -> str:
    """Remove Outlook conditional markers, including escaped/plain-text remnants."""
    text = re.sub(r"&lt;!--(.*?)--&gt;", r"<!--\1-->", text, flags=re.S)
    text = re.sub(r"<!--\s*\[if[^\]]*\]\s*>", "", text, flags=re.I)
    text = re.sub(r"<!\s*\[endif\]\s*-->|<!--\s*<!\[endif\]\s*-->", "", text, flags=re.I)
    return re.sub(r"<!--.*?-->|<!-->|<!--\s*-->", "", text, flags=re.S)


def _decode_base64url(data: str) -> bytes:
    # Gmail's body data is base64url without padding; re-pad before decoding.
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded)


class _HTMLToTextParser(HTMLParser):
    """Minimal HTML -> text conversion: drop tags/scripts/styles, keep line breaks."""

    _BLOCK_TAGS = {"br", "p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}
    _SKIP_TAGS = {"script", "style"}

    def __init__(self):
        super().__init__()
        self._chunks = []
        self._skip_depth = 0
        self._stack = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        style = re.sub(r"\s+", "", attrs.get("style", "").lower())
        hidden = (self._skip_depth > 0 or tag in self._SKIP_TAGS
                  or "hidden" in attrs or "display:none" in style
                  or "visibility:hidden" in style or "mso-hide:all" in style)
        if tag not in {"br", "hr", "img", "meta", "link", "input", "wbr", "area", "base", "col", "embed", "param", "source", "track"}:
            self._stack.append((tag, hidden))
            self._skip_depth += int(hidden)
        if not hidden and tag in self._BLOCK_TAGS:
            self._chunks.append("\n")

    def handle_endtag(self, tag):
        for index in range(len(self._stack) - 1, -1, -1):
            if self._stack[index][0] == tag:
                self._skip_depth -= sum(int(hidden) for _, hidden in self._stack[index:])
                del self._stack[index:]
                break
        if self._skip_depth == 0 and tag in self._BLOCK_TAGS:
            self._chunks.append("\n")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_data(self, data):
        if self._skip_depth == 0:
            self._chunks.append(data)

    def get_text(self):
        return "".join(self._chunks)


def html_to_text(html: str) -> str:
    parser = _HTMLToTextParser()
    parser.feed(clean_template_comments(html))
    text = clean_template_comments(unescape(parser.get_text()))
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]*\n+", "\n\n", text)
    return text.strip()


def _iter_leaf_parts(payload: dict):
    """Yields (mime_type, base64url_data) for every part that actually has body data."""
    parts = payload.get("parts")
    if parts:
        for part in parts:
            yield from _iter_leaf_parts(part)
        return

    data = payload.get("body", {}).get("data")
    if data:
        yield payload.get("mimeType", ""), data


def parse_email_body(message: dict) -> str:
    """
    Returns clean plain-text body for a Gmail message resource.

    Prefers text/plain parts (there may be several, e.g. one per
    multipart/alternative branch that has one); falls back to converting
    text/html to text if no plain-text part exists. Attachments (parts
    with no inline body 'data', only an 'attachmentId') are skipped
    entirely — this is a text/summarization pipeline, not a file store.
    """
    payload = message.get("payload", {})

    plain_chunks = []
    html_chunks = []

    for mime_type, data in _iter_leaf_parts(payload):
        try:
            decoded = _decode_base64url(data).decode("utf-8", errors="replace")
        except (ValueError, UnicodeDecodeError):
            continue

        if mime_type == "text/plain":
            plain_chunks.append(decoded)
        elif mime_type == "text/html":
            html_chunks.append(decoded)

    if plain_chunks:
        return clean_template_comments("\n\n".join(chunk.strip() for chunk in plain_chunks)).strip()
    if html_chunks:
        return html_to_text("\n".join(html_chunks))
    return ""
