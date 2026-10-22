from datetime import datetime, timedelta, timezone
from tests.test_review_fixes import app, seed_email, authenticated_client


def test_deadlines_page_filters_and_ownership(app):
    from app.extensions import db
    from app.models import Reminder, User
    user, email = seed_email()
    other = User(google_id="deadline-other", email="other@example.com")
    db.session.add(other)
    db.session.flush()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for owner, text, days, dismissed in [(user, "Future task", 2, False),
            (user, "Past task", -2, False), (user, "Dismissed task", 3, True),
            (other, "Private task", 2, False)]:
        db.session.add(Reminder(user_id=owner.id, email_id=email.id, description=text,
                               deadline_at=now + timedelta(days=days), is_dismissed=dismissed))
    db.session.commit()
    client = authenticated_client(app, user)
    upcoming = client.get("/deadlines")
    assert upcoming.status_code == 200
    assert b"Future task" in upcoming.data
    assert b"Past task" not in upcoming.data and b"Dismissed task" not in upcoming.data
    assert b"Private task" not in upcoming.data
    assert b'class="sidebar-link active" href="/deadlines"' in upcoming.data
    overdue = client.get("/deadlines?view=overdue").data
    assert b"Past task" in overdue and b"Future task" not in overdue
    history = client.get("/deadlines?view=all").data
    assert all(text in history for text in [b"Future task", b"Past task", b"Dismissed task"])
    assert b"Private task" not in history
    assert client.get("/deadlines?view=invalid").status_code == 400
    assert app.test_client().get("/deadlines").status_code == 401
