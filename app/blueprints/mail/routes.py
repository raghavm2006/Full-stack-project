import json
import secrets
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, session, url_for
from app.blueprints.auth.decorators import login_required
from app.blueprints.gmail.gmail_client import get_credentials_for_user, build_gmail_service
from app.blueprints.mail.service import build_message, reply_defaults, read_attachments, saved_attachments, check_reply, record_sent
from app.extensions import db
from app.models import Email, User, OutgoingMessage

mail_bp = Blueprint("mail", __name__, url_prefix="/mail")


def csrf_token():
    if "mail_csrf" not in session:
        session["mail_csrf"] = secrets.token_urlsafe(32)
    return session["mail_csrf"]


def validate_csrf():
    expected = session.get("mail_csrf", "")
    supplied = request.form.get("csrf_token", "")
    if not expected or not secrets.compare_digest(expected.encode(), supplied.encode()):
        abort(400, description="Form expired. Reload the page and try again.")


def owner():
    return db.session.get(User, session["user_id"]) or abort(401)


def owned_email(value):
    if not value:
        return None
    try:
        value = int(value)
    except ValueError:
        abort(400)
    return Email.query.filter_by(id=value, user_id=session["user_id"]).first_or_404()


def owned_outgoing(item_id):
    return OutgoingMessage.query.filter_by(id=item_id, user_id=session["user_id"]).first_or_404()


@mail_bp.get("/compose")
@login_required
def compose():
    user = owner()
    reply = owned_email(request.args.get("reply_to"))
    fields = {"to": "", "cc": "", "bcc": "", "subject": "", "body": ""}
    outgoing = None
    if request.args.get("edit"):
        try:
            outgoing = owned_outgoing(int(request.args["edit"]))
        except ValueError:
            abort(400)
        if outgoing.status not in {"prepared", "draft"}:
            abort(409, description="This message cannot be edited in its current state.")
        reply = owned_email(outgoing.reply_email_id)
        fields = {"to": outgoing.recipients, "cc": outgoing.cc, "bcc": outgoing.bcc,
                  "subject": outgoing.subject, "body": outgoing.body}
    elif reply:
        try:
            fields.update(reply_defaults(reply, user))
        except ValueError as exc:
            flash(str(exc), "warning")
    history = OutgoingMessage.query.filter_by(user_id=user.id).order_by(OutgoingMessage.id.desc()).limit(30).all()
    suggestions = []
    if reply:
        try:
            suggestions = json.loads(reply.smart_replies or "[]")
            if not isinstance(suggestions, list):
                suggestions = []
        except ValueError:
            pass
    return render_template("mail/compose.html", fields=fields, reply=reply, outgoing=outgoing,
                           history=history, suggestions=suggestions, csrf_token=csrf_token())


@mail_bp.post("/prepare")
@login_required
def prepare():
    # Bound multipart uploads for this feature without changing other endpoints.
    if request.content_length and request.content_length > 15 * 1024 * 1024:
        abort(413, description="Message upload is too large (attachments: 10 MB total).")
    validate_csrf()
    user = owner()
    reply = owned_email(request.form.get("reply_email_id"))
    previous = None
    if request.form.get("edit_id"):
        try:
            previous = owned_outgoing(int(request.form["edit_id"]))
        except ValueError:
            abort(400)
        if previous.status not in {"prepared", "draft"} or previous.reply_email_id != (reply.id if reply else None):
            abort(409)
    try:
        existing = saved_attachments(previous) if previous and request.form.get("keep_attachments") == "1" else []
        attachments = read_attachments(request.files.getlist("attachments"), existing)
        values = build_message(user, request.form, attachments, reply)
    except ValueError as exc:
        # Preserve entered text on validation errors; browsers require file reselection.
        return render_template("mail/compose.html", fields=request.form, reply=reply, outgoing=previous,
                               history=[], suggestions=[], csrf_token=csrf_token(), error=str(exc)), 400
    if previous:
        # Conditional update blocks an edit racing with a send of the old preview.
        changed = OutgoingMessage.query.filter(OutgoingMessage.id == previous.id,
            OutgoingMessage.status.in_(["prepared", "draft"])).update({"status": "replaced"}, synchronize_session=False)
        if changed != 1:
            db.session.rollback()
            abort(409)
    message = OutgoingMessage(user_id=user.id, reply_email_id=reply.id if reply else None,
                              gmail_draft_id=previous.gmail_draft_id if previous else None, **values)
    db.session.add(message)
    db.session.commit()
    return redirect(url_for("mail.preview", item_id=message.id))


@mail_bp.get("/preview/<int:item_id>")
@login_required
def preview(item_id):
    message = owned_outgoing(item_id)
    reply = owned_email(message.reply_email_id)
    return render_template("mail/preview.html", message=message, attachments=json.loads(message.attachments),
                           checks=check_reply(reply, message.body), csrf_token=csrf_token())


@mail_bp.post("/<int:item_id>/<action>")
@login_required
def deliver(item_id, action):
    validate_csrf()
    user, message = owner(), owned_outgoing(item_id)
    if action not in {"send", "draft"}:
        abort(404)
    if (action == "send" and not user.gmail_send_granted) or (action == "draft" and not user.gmail_drafts_granted):
        abort(403, description="Enable the required Gmail permission from the preview first.")
    if message.gmail_draft_id and not user.gmail_drafts_granted:
        abort(403, description="Reconnect Gmail drafts permission before sending this Gmail draft.")
    if request.form.get("confirm") != "yes":
        abort(400, description="Explicit confirmation is required.")
    expected = {"prepared", "draft"} if action == "send" else {"prepared"}
    # Resolve credentials BEFORE reserving the attempt: a token refresh failure
    # cannot have delivered the message.
    try:
        credentials = get_credentials_for_user(user, current_app.config["GOOGLE_CLIENT_ID"], current_app.config["GOOGLE_CLIENT_SECRET"])
        service = build_gmail_service(credentials)
    except Exception:
        flash("Could not connect to Gmail. Reconnect permissions and try again; no message was submitted.", "warning")
        return redirect(url_for("mail.preview", item_id=message.id))
    reserved = OutgoingMessage.query.filter(OutgoingMessage.id == item_id,
        OutgoingMessage.user_id == user.id, OutgoingMessage.status.in_(expected)).update(
            {"status": "sending" if action == "send" else "saving"}, synchronize_session=False)
    if reserved != 1:
        db.session.rollback()
        abort(409, description="This message has already been submitted or is no longer editable.")
    db.session.commit()
    payload = {"raw": message.raw_message}
    if message.thread_id:
        payload["threadId"] = message.thread_id
    try:
        if action == "send":
            if message.gmail_draft_id:
                result = service.users().drafts().send(userId="me", body={"id": message.gmail_draft_id, "message": payload}).execute(num_retries=0)
            else:
                result = service.users().messages().send(userId="me", body=payload).execute(num_retries=0)
            if not result.get("id"):
                raise ValueError("Missing Gmail receipt")
            message.gmail_message_id, message.status = result["id"], "sent"
            record_sent(user, message, result)
        else:
            if message.gmail_draft_id:
                result = service.users().drafts().update(userId="me", id=message.gmail_draft_id, body={"message": payload}).execute(num_retries=0)
            else:
                result = service.users().drafts().create(userId="me", body={"message": payload}).execute(num_retries=0)
            if not result.get("id"):
                raise ValueError("Missing Gmail draft receipt")
            message.gmail_draft_id, message.status = result["id"], "draft"
        db.session.commit()
    except Exception:
        db.session.rollback()
        message = owned_outgoing(item_id)
        message.status = "uncertain"
        db.session.commit()
        flash("Gmail did not confirm the result. Check Gmail Sent/Drafts before composing another copy. Automatic retry is disabled.", "warning")
        return redirect(url_for("mail.preview", item_id=item_id))
    flash("Email sent." if action == "send" else "Draft saved to Gmail. Nothing was sent.", "success")
    if action == "send":
        try:
            from app.blueprints.followup.service import detect_pending_follow_ups
            from app.blueprints.commitments.service import scan_commitments
            detect_pending_follow_ups(user.id)
            scan_commitments(user)
        except Exception:
            db.session.rollback()
            flash("Email was sent. Some tracking updates will refresh on the next sync.", "warning")
    return redirect(url_for("mail.preview", item_id=item_id))
