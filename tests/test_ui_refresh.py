"""Search/sort and reading-pane regressions using the normal authenticated routes."""
from datetime import timedelta

from tests.test_review_fixes import app, seed_email, authenticated_client


def test_spam_overview_and_filters_are_user_scoped(app):
    from app.extensions import db
    from app.models import Email, User

    user, email = seed_email()
    email.spam_label = True
    other = User(google_id="other-spam-user", email="other@example.com")
    db.session.add(other)
    db.session.flush()
    for owner, message, label in [(user, "ham", False), (user, "pending", None),
                                   (other, "private-spam", True)]:
        db.session.add(Email(user_id=owner.id, gmail_message_id=message, thread_id=message,
                             sender="sender@example.com", timestamp=email.timestamp,
                             spam_label=label))
    db.session.commit()
    client = authenticated_client(app, user)
    assert client.get("/dashboard/stats").get_json()["spam_emails"] == 1
    spam = client.get("/emails?spam_label=true").get_json()
    assert [row["id"] for row in spam["emails"]] == [email.id]
    ham = client.get("/emails?spam_label=false").get_json()
    assert ham["total"] == 1
    assert ham["emails"][0]["spam_label"] is False
    assert client.get("/emails").get_json()["total"] == 3
    assert client.get("/emails?spam_label=invalid").status_code == 400
    dashboard = client.get("/dashboard").data
    assert b'data-stat="spam_emails"' in dashboard
    assert b'/inbox?spam_label=true' in dashboard
    assert b'id="spamFilter"' in client.get("/inbox?spam_label=true").data


def test_search_and_sort_remain_user_scoped(app):
    from app.extensions import db
    from app.models import Email, User

    user, email = seed_email()
    email.body = "Project budget 100% complete"
    email.priority = "LOW"
    second = Email(user_id=user.id, gmail_message_id="second", thread_id="second",
                   sender="manager@example.com", subject="Budget review", body="Please review",
                   priority="HIGH", timestamp=email.timestamp + timedelta(days=1))
    other = User(google_id="private-user", email="private@example.com")
    db.session.add_all([second, other])
    db.session.flush()
    db.session.add(Email(user_id=other.id, gmail_message_id="private", thread_id="private",
                         sender="manager@example.com", subject="Budget", body="private",
                         timestamp=email.timestamp))
    db.session.commit()
    client = authenticated_client(app, user)
    results = client.get("/emails?q=budget&sort=priority").get_json()["emails"]
    assert [row["id"] for row in results] == [second.id, email.id]
    assert client.get("/emails?q=100%25").get_json()["total"] == 1
    assert client.get("/emails?q=manager").get_json()["total"] == 1
    results = client.get("/emails?sort=oldest").get_json()["emails"]
    assert results[0]["id"] == email.id


def test_preview_keeps_detail_controls_and_user_isolation(app):
    from app.extensions import db
    from app.models import Email, User

    user, email = seed_email()
    client = authenticated_client(app, user)
    response = client.get(f"/inbox/{email.id}?preview=1")
    assert response.status_code == 200
    assert b'id="toggleReadBtn"' in response.data
    assert b'id="categoryCorrection"' in response.data
    assert b'class="app-sidebar"' not in response.data
    other = User(google_id="private-user", email="private@example.com")
    db.session.add(other)
    db.session.flush()
    private = Email(user_id=other.id, gmail_message_id="private", thread_id="private",
                    sender="private@example.com", body="private content", timestamp=email.timestamp)
    db.session.add(private)
    db.session.commit()
    assert client.get(f"/inbox/{private.id}?preview=1").status_code == 302
