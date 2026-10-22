"""Render email text and original HTML links without rendering email HTML."""
import json
import re
from urllib.parse import urlsplit

from jinja2.utils import urlize
from markupsafe import Markup, escape

from app.blueprints.emails.parser import (
    _HTMLToTextParser, _iter_leaf_parts, _decode_base64url, clean_template_comments,
)


def _compact_spacing(text):
    """Keep paragraph breaks, but discard email-template spacer lines."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", text)
    text = re.sub(r"(?m)^[ \t]+$", "", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


class _LinkedTextParser(_HTMLToTextParser):
    def __init__(self):
        super().__init__()
        self._anchors = []

    def handle_starttag(self, tag, attrs):
        super().handle_starttag(tag, attrs)
        if tag == "a":
            href = dict(attrs).get("href") or ""
            try:
                parsed = urlsplit(href)
                allowed = parsed.scheme.lower() in {"http", "https"} and bool(parsed.hostname)
            except ValueError:
                allowed = False
            linked = allowed and self._skip_depth == 0
            self._anchors.append(linked)
            if linked:
                self._chunks.append(f'<a href="{escape(href)}" target="_blank" rel="noopener noreferrer">')

    def handle_endtag(self, tag):
        if tag == "a" and self._anchors and self._anchors.pop():
            self._chunks.append("</a>")
        super().handle_endtag(tag)
        if tag in {"td", "th"} and self._skip_depth == 0:
            self._chunks.append(" ")

    def handle_data(self, data):
        if self._skip_depth == 0:
            # HTML source indentation/newlines are not visible line breaks.
            # Structural breaks are inserted separately by the parser.
            data = re.sub(r"\s+", " ", data)
            if any(self._anchors):
                self._chunks.append(str(escape(data)))
            else:
                self._chunks.append(str(urlize(data, target="_blank", rel="noopener noreferrer")))


def linked_email_body(email):
    # Recover labelled links (e.g. "View invoice") from the saved Gmail
    # payload. Never pass sender-supplied HTML through to the browser.
    try:
        message = json.loads(email.raw_payload or "{}")
        html_parts = [
            _decode_base64url(data).decode("utf-8", errors="replace")
            for mime, data in _iter_leaf_parts(message.get("payload", {}))
            if mime == "text/html"
        ]
        if html_parts:
            parser = _LinkedTextParser()
            parser.feed(clean_template_comments("\n".join(html_parts)))
            parser.close()
            while parser._anchors:
                if parser._anchors.pop():
                    parser._chunks.append("</a>")
            rendered = _compact_spacing(parser.get_text())
            if rendered:
                return Markup(rendered)
    except (ValueError, TypeError, AttributeError):
        pass
    return Markup(urlize(_compact_spacing(email.body or "(no content)"), target="_blank", rel="noopener noreferrer"))
