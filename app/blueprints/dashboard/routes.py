"""
Phase 5: dashboard + inbox page routes, plus the /dashboard/stats JSON
endpoint the dashboard page's Chart.js code reads from.

This blueprint owns every server-rendered HTML page in the app (landing,
dashboard, inbox list, inbox detail) — auth/gmail/emails blueprints stay
pure JSON APIs that these pages' own JavaScript calls via fetch(), which
is why /inbox and /inbox/<id> live here rather than under the emails
blueprint's /emails prefix.
"""

from datetime import datetime, timezone

from flask import Blueprint, jsonify, redirect, render_template, session, url_for, request, abort

from app.blueprints.auth.decorators import login_required
from app.extensions import db
from app.models import Email, Reminder, Commitment

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
def landing_page():
    if session.get("user_id"):
        return redirect(url_for("dashboard.dashboard_page"))
    return render_template("dashboard/landing.html")


@dashboard_bp.route("/dashboard")
@login_required
def dashboard_page():
    reminders = (Reminder.query.filter_by(user_id=session["user_id"], is_dismissed=False)
                 .filter(Reminder.deadline_at >= datetime.now(timezone.utc))
                 .order_by(Reminder.deadline_at.asc()).limit(5).all())
    return render_template("dashboard/dashboard.html", upcoming_reminders=reminders)


@dashboard_bp.route("/dashboard/stats")
@login_required
def dashboard_stats():
    user_id = session["user_id"]
    from app.blueprints.commitments.timing import commitment_timing
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    overdue_commitments = sum(
        1 for item in Commitment.query.filter(Commitment.user_id == user_id,
                                               Commitment.status.in_(["proposed", "active"])).all()
        if (at := commitment_timing(item)["at"]) is not None and at < now
    )

    total_emails = Email.query.filter_by(user_id=user_id).count()
    unread_emails = Email.query.filter_by(user_id=user_id, is_read=False).count()
    high_priority_emails = Email.query.filter_by(user_id=user_id, priority="HIGH").count()

    # Phase 10: real counts from followup/service.py + deduplication/
    # service.py, both recomputed at the end of every Gmail sync.
    pending_replies = Email.query.filter_by(user_id=user_id, needs_follow_up=True).count()
    duplicate_emails = Email.query.filter_by(user_id=user_id, is_duplicate=True).count()

    upcoming_deadlines = Reminder.query.filter_by(
        user_id=user_id, is_dismissed=False
    ).filter(Reminder.deadline_at >= datetime.now(timezone.utc)).count()

    category_counts = (
        db.session.query(Email.category, db.func.count(Email.id))
        .filter(Email.user_id == user_id)
        .group_by(Email.category)
        .all()
    )
    category_breakdown = {
        (category or "Uncategorized"): count for category, count in category_counts
    }

    return jsonify({
        "total_emails": total_emails,
        "unread_emails": unread_emails,
        "high_priority_emails": high_priority_emails,
        "pending_replies": pending_replies,
        "upcoming_deadlines": upcoming_deadlines,
        "duplicate_emails": duplicate_emails,
        "spam_emails": Email.query.filter_by(user_id=user_id, spam_label=True).count(),
        "overdue_commitments": overdue_commitments,
        "category_breakdown": category_breakdown,
    })


@dashboard_bp.route("/inbox")
@login_required
def inbox_page():
    return render_template("emails/inbox.html")


@dashboard_bp.get("/deadlines")
@login_required
def deadlines_page():
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    view = request.args.get("view", "upcoming")
    query = Reminder.query.filter_by(user_id=session["user_id"])
    if view == "upcoming":
        query = query.filter(Reminder.is_dismissed.is_(False), Reminder.deadline_at >= now)
    elif view == "overdue":
        query = query.filter(Reminder.is_dismissed.is_(False), Reminder.deadline_at < now)
    elif view != "all":
        abort(400)
    return render_template("dashboard/deadlines.html", reminders=query.order_by(Reminder.deadline_at.asc()).all(),
                           now=now, view=view)


@dashboard_bp.route("/inbox/<int:email_id>")
@login_required
def email_detail_page(email_id):
    email = Email.query.filter_by(id=email_id, user_id=session["user_id"]).first()
    if email is None:
        return redirect(url_for("dashboard.inbox_page"))

    from app.blueprints.nlp_features.insights import key_information
    from app.blueprints.ml_inference.review import category_evidence
    return render_template("emails/email_detail.html", email=email, key_info=key_information(email),
                           category_review=category_evidence(email))


@dashboard_bp.route("/health")
def health():
    """Verifies the app can actually talk to MySQL, not just that Flask is up."""
    try:
        db.session.execute(db.text("SELECT 1"))
        db_status = "connected"
    except Exception as exc:  # noqa: BLE001 - deliberately broad for a health check
        db_status = f"error: {exc}"

    return jsonify({"database": db_status})
