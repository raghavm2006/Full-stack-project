from app.blueprints.emails.parser import html_to_text, clean_template_comments
from app.blueprints.nlp_features.summarizer import summarize_text


def test_conditional_markers_are_removed_without_losing_message():
    text = "Account connected. <!--[if !mso]><!-- --> <!--[if false]> Profile shared. <![endif]-->"
    result = summarize_text(text)
    assert "Account connected." in result
    assert "Profile shared." in result
    assert "<!--" not in result
    assert "endif" not in result


def test_html_hidden_preheader_and_nested_content_are_excluded():
    html = '<div style="display: none"><span>Hidden preview</span></div><p>Account connected.</p><p>Review permissions.</p>'
    result = html_to_text(html)
    assert "Hidden preview" not in result
    assert "Account connected." in result
    assert "Review permissions." in result
    assert "\n" in result


def test_summary_deduplicates_lines_and_limits_unpunctuated_text():
    assert summarize_text("Account connected.\nAccount connected.\nReview permissions.") == "Account connected. Review permissions."
    result = summarize_text("Account details " * 100)
    assert len(result) <= 1000
    assert result.endswith("…")


def test_cleanup_preserves_plain_text_comparisons_and_negation():
    assert clean_template_comments("Balance < 100. Do not pay again.") == "Balance < 100. Do not pay again."
    assert summarize_text("Do not pay again.") == "Do not pay again."


def test_summary_keeps_context_and_complementary_details():
    text = (
        "Your project application has been accepted.\n"
        "The orientation is on Monday at 10 AM.\n"
        "Please submit your identity documents before Friday.\n"
        "The participation fee is 250 rupees.\n"
        "Do not send original documents.\n"
        "Contact the coordinator if you need help."
    )
    assert summarize_text(text) == " ".join(text.splitlines())


def test_custom_summary_budget_and_complete_sentences():
    text = "Your application is accepted. Please confirm by Friday. The fee is 250 rupees."
    result = summarize_text(text, max_sentences=2, max_chars=75)
    assert len(result) <= 75
    assert "Friday" in result or "250" in result
    assert result.endswith(".")
