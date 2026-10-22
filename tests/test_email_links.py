import base64
import json
from types import SimpleNamespace

from app.utils.email_links import linked_email_body


def email_with_html(html):
    data = base64.urlsafe_b64encode(html.encode()).decode()
    return SimpleNamespace(body="Fallback", raw_payload=json.dumps({
        "payload": {"mimeType": "text/html", "body": {"data": data}}
    }))


def test_plain_urls_clickable_and_html_escaped():
    email = SimpleNamespace(body='Visit https://example.com/path <script>alert(1)</script>', raw_payload=None)
    result = str(linked_email_body(email))
    assert 'href="https://example.com/path"' in result
    assert 'target="_blank"' in result
    assert 'noopener noreferrer' in result
    assert '<script>' not in result


def test_labelled_links_recovered_without_sender_html():
    email = email_with_html('<p><a href="https://example.com/invoice?a=1&amp;b=2" onclick="bad()">View invoice</a></p>'
                            '<script>alert(1)</script><img src="https://tracking.example/pixel">')
    result = str(linked_email_body(email))
    assert 'href="https://example.com/invoice?a=1&amp;b=2"' in result
    assert '>View invoice</a>' in result
    assert 'onclick' not in result
    assert '<script' not in result
    assert '<img' not in result


def test_unsafe_links_and_hidden_content_excluded():
    result = str(linked_email_body(email_with_html(
        '<a href="javascript:alert(1)">Unsafe</a>'
        '<div hidden><a href="https://example.com/hidden">Hidden</a></div>'
        '<p>https://example.com/visible</p>'
    )))
    assert 'javascript:' not in result
    assert 'Hidden' not in result
    assert 'href="https://example.com/visible"' in result


def test_invalid_payload_falls_back_to_body():
    email = SimpleNamespace(body='https://example.com', raw_payload='not json')
    assert 'href="https://example.com"' in str(linked_email_body(email))


def test_html_spacer_rows_and_source_indentation_are_compacted():
    result = str(linked_email_body(email_with_html(
        '<div>Welcome</div>\n\n\n    <div>&nbsp;</div><p><br><br><br></p>'
        '<table><tr><td>&nbsp;</td></tr><tr><td>Dear reader,</td></tr></table>'
        '<p>Please\n    verify your account.</p>'
        '<a href="https://example.com/verify">Verify account</a>'
    )))
    assert '\n\n\n' not in result
    assert 'Please verify your account.' in result
    assert 'Dear reader,' in result
    assert '>Verify account</a>' in result
    assert 'href="https://example.com/verify"' in result


def test_plain_text_spacing_preserves_paragraphs_and_list_lines():
    email = SimpleNamespace(raw_payload=None, body=(
        'Hello\r\n\r\n \t\r\n\u00a0\r\n\r\n'
        'Details:\r\n- First item\r\n- Second item\r\n\r\nRegards'
    ))
    result = str(linked_email_body(email))
    assert result == 'Hello\n\nDetails:\n- First item\n- Second item\n\nRegards'
