"""
Phase 4 verification tests for app/blueprints/emails/parser.py.

Run with: pytest tests/test_email_parser.py -v
"""

import base64

from app.blueprints.emails.parser import html_to_text, parse_email_body


def _b64url(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def test_parses_simple_plain_text_message():
    message = {
        "payload": {
            "mimeType": "text/plain",
            "body": {"data": _b64url("Hello, this is a plain message.")},
        }
    }
    assert parse_email_body(message) == "Hello, this is a plain message."


def test_prefers_plain_text_part_over_html_in_multipart_alternative():
    message = {
        "payload": {
            "mimeType": "multipart/alternative",
            "parts": [
                {"mimeType": "text/plain", "body": {"data": _b64url("Plain version")}},
                {"mimeType": "text/html", "body": {"data": _b64url("<p>HTML version</p>")}},
            ],
        }
    }
    assert parse_email_body(message) == "Plain version"


def test_falls_back_to_html_when_no_plain_text_part_exists():
    message = {
        "payload": {
            "mimeType": "multipart/alternative",
            "parts": [
                {"mimeType": "text/html", "body": {"data": _b64url("<p>Only HTML here</p>")}},
            ],
        }
    }
    assert parse_email_body(message) == "Only HTML here"


def test_skips_attachment_parts_with_no_inline_data():
    message = {
        "payload": {
            "mimeType": "multipart/mixed",
            "parts": [
                {"mimeType": "text/plain", "body": {"data": _b64url("Main message")}},
                {
                    "mimeType": "application/pdf",
                    "filename": "invoice.pdf",
                    "body": {"attachmentId": "abc123", "size": 45000},
                },
            ],
        }
    }
    assert parse_email_body(message) == "Main message"


def test_handles_nested_multipart_structure():
    message = {
        "payload": {
            "mimeType": "multipart/mixed",
            "parts": [
                {
                    "mimeType": "multipart/alternative",
                    "parts": [
                        {"mimeType": "text/plain", "body": {"data": _b64url("Nested plain text")}},
                        {"mimeType": "text/html", "body": {"data": _b64url("<p>Nested HTML</p>")}},
                    ],
                },
                {
                    "mimeType": "application/pdf",
                    "filename": "report.pdf",
                    "body": {"attachmentId": "xyz789"},
                },
            ],
        }
    }
    assert parse_email_body(message) == "Nested plain text"


def test_returns_empty_string_when_no_body_data_anywhere():
    message = {"payload": {"mimeType": "multipart/mixed", "parts": []}}
    assert parse_email_body(message) == ""


def test_html_to_text_strips_tags_and_scripts():
    html = "<html><body><script>evil()</script><p>Hello <b>World</b></p></body></html>"
    text = html_to_text(html)
    assert "evil()" not in text
    assert "Hello" in text and "World" in text


def test_html_to_text_preserves_paragraph_breaks():
    html = "<p>First paragraph</p><p>Second paragraph</p>"
    text = html_to_text(html)
    assert "First paragraph" in text
    assert "Second paragraph" in text
    # There should be some line break separating the two paragraphs.
    assert "\n" in text
