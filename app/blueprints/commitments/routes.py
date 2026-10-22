from datetime import datetime, timezone
from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from app.blueprints.auth.decorators import login_required
from app.extensions import db
from app.models import Commitment, Email, User
from app.blueprints.commitments.service import scan_commitments
from app.blueprints.nlp_features.insights import message_sentences
from app.blueprints.nlp_features.summarizer import summarize_text
import secrets

commitments_bp = Blueprint("commitments", __name__, url_prefix="/commitments")


def form_token():
    if "commitment_csrf" not in session:
        session["commitment_csrf"] = secrets.token_urlsafe(32)
    return session["commitment_csrf"]


def validate_form():
    expected = session.get("commitment_csrf", "")
    supplied = request.form.get("csrf_token", "")
    if not expected or not secrets.compare_digest(expected.encode(), supplied.encode()):
        abort(400, description="Form expired. Reload the page and try again.")


@commitments_bp.get("")
@login_required
def index():
    from app.blueprints.commitments.timing import commitment_timing
    items = Commitment.query.filter_by(user_id=session["user_id"]).order_by(Commitment.created_at.desc()).all()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    timings = {item.id: commitment_timing(item) for item in items}
    view = request.args.get("view", "open")
    def expired(item):
        at = timings[item.id]["at"]
        return at is not None and at < now
    if view == "open":
        visible = [item for item in items if item.status in {"proposed", "active"} and not expired(item)]
    elif view == "overdue":
        visible = [item for item in items if item.status in {"proposed", "active"} and expired(item)]
    elif view == "all":
        visible = items
    else:
        abort(400)
    return render_template("commitments/index.html", commitments=visible, timings=timings,
                           replacement_candidates=[item for item in items if item.status == "active"],
                           view=view, csrf_token=form_token(), now=now)


@commitments_bp.post("/scan")
@login_required
def scan():
    validate_form()
    user = db.session.get(User, session["user_id"])
    if not user:
        abort(401)
    count = scan_commitments(user)
    flash(f"Found {count} new proposed commitments. Review before confirming.", "success")
    return redirect(url_for("commitments.index"))


@commitments_bp.post("/<int:item_id>")
@login_required
def update(item_id):
    validate_form()
    item = Commitment.query.filter_by(id=item_id, user_id=session["user_id"]).first_or_404()
    status = request.form.get("status", "")
    if status not in {"active", "completed", "dismissed"}:
        abort(400)
    description = request.form.get("description", item.description).strip()
    responsible = request.form.get("responsible", item.responsible)
    if not description or len(description) > 2000 or responsible not in {"me", "other"}:
        abort(400)
    deadline = item.deadline_at
    if "deadline" in request.form:
        value = request.form["deadline"].strip()
        try:
            deadline = datetime.fromisoformat(value) if value else None
            if deadline and deadline.tzinfo:
                deadline = deadline.astimezone(timezone.utc).replace(tzinfo=None)
        except ValueError:
            abort(400, description="Enter a valid UTC date/time.")
    previous = None
    if request.form.get("supersedes_id"):
        try:
            previous_id = int(request.form["supersedes_id"])
        except ValueError:
            abort(400)
        previous = Commitment.query.filter_by(id=previous_id, user_id=item.user_id,
                                               thread_id=item.thread_id, status="active").first()
        if not previous or previous.id == item.id or status != "active" or item.status != "proposed":
            abort(400, description="Select an active commitment in the same conversation.")
        if previous.source_email.timestamp > item.source_email.timestamp:
            abort(400, description="A newer commitment cannot be replaced by an older proposal.")
    if item.status in {"completed", "dismissed", "superseded"}:
        abort(400, description="This commitment is already closed.")
    item.description, item.responsible, item.deadline_at, item.status = description, responsible, deadline, status
    if previous:
        previous.status = "superseded"
        item.supersedes_id = previous.id
    db.session.commit()
    flash("Commitment updated.", "success")
    return redirect(url_for("commitments.index"))


@commitments_bp.get("/thread/<int:email_id>")
@login_required
def thread(email_id):
    email = Email.query.filter_by(id=email_id, user_id=session["user_id"]).first_or_404()
    emails = Email.query.filter_by(user_id=email.user_id, thread_id=email.thread_id).order_by(Email.timestamp, Email.id).all()
    entries = [{"email": message, "summary": summarize_text("\n".join(message_sentences(message)),
                                                           max_sentences=3, max_chars=600)} for message in emails]
    items = Commitment.query.filter_by(user_id=email.user_id, thread_id=email.thread_id).order_by(Commitment.created_at).all()
    return render_template("commitments/thread.html", entries=entries, commitments=items, email=email)
