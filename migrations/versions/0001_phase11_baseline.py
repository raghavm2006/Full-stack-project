"""Baseline of the delivered Phase 11 schema (original history unavailable)."""
from alembic import op
import sqlalchemy as sa

revision = "phase11_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('users',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('google_id', sa.String(255), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('name', sa.String(255), nullable=True),
        sa.Column('profile_picture_url', sa.String(512), nullable=True),
        sa.Column('oauth_token_encrypted', sa.Text, nullable=True),
        sa.Column('oauth_refresh_token_encrypted', sa.Text, nullable=True),
        sa.Column('oauth_token_expiry', sa.DateTime, nullable=True),
        sa.Column('gmail_scope_granted', sa.Boolean, nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('last_synced_at', sa.DateTime, nullable=True),
    )
    op.create_index("ix_users_google_id", 'users', ['google_id'], unique=True)
    op.create_index("ix_users_email", 'users', ['email'], unique=True)
    op.create_table('emails',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id'), nullable=False),
        sa.Column('gmail_message_id', sa.String(64), nullable=False),
        sa.Column('thread_id', sa.String(64), nullable=False),
        sa.Column('sender', sa.String(320), nullable=False),
        sa.Column('receiver', sa.String(320), nullable=True),
        sa.Column('subject', sa.String(998), nullable=True),
        sa.Column('body', sa.Text, nullable=True),
        sa.Column('timestamp', sa.DateTime, nullable=False),
        sa.Column('category', sa.String(32), nullable=True),
        sa.Column('category_confidence', sa.Float, nullable=True),
        sa.Column('priority', sa.String(16), nullable=True),
        sa.Column('priority_confidence', sa.Float, nullable=True),
        sa.Column('spam_label', sa.Boolean, nullable=True),
        sa.Column('spam_probability', sa.Float, nullable=True),
        sa.Column('summary', sa.Text, nullable=True),
        sa.Column('smart_replies', sa.Text, nullable=True),
        sa.Column('smart_reply_source', sa.String(16), nullable=True),
        sa.Column('needs_follow_up', sa.Boolean, nullable=False),
        sa.Column('content_hash', sa.String(64), nullable=True),
        sa.Column('is_duplicate', sa.Boolean, nullable=False),
        sa.Column('duplicate_of_email_id', sa.Integer, sa.ForeignKey('emails.id'), nullable=True),
        sa.Column('is_read', sa.Boolean, nullable=False),
        sa.Column('raw_payload', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.UniqueConstraint('user_id', 'gmail_message_id', name='uq_user_gmail_message'),
    )
    op.create_index("ix_emails_user_id", 'emails', ['user_id'], unique=False)
    op.create_index("ix_emails_gmail_message_id", 'emails', ['gmail_message_id'], unique=False)
    op.create_index("ix_emails_thread_id", 'emails', ['thread_id'], unique=False)
    op.create_index("ix_emails_timestamp", 'emails', ['timestamp'], unique=False)
    op.create_index("ix_emails_category", 'emails', ['category'], unique=False)
    op.create_index("ix_emails_priority", 'emails', ['priority'], unique=False)
    op.create_index("ix_emails_spam_label", 'emails', ['spam_label'], unique=False)
    op.create_index("ix_emails_content_hash", 'emails', ['content_hash'], unique=False)
    op.create_table('actions',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id'), nullable=False),
        sa.Column('email_id', sa.Integer, sa.ForeignKey('emails.id'), nullable=False),
        sa.Column('description', sa.Text, nullable=False),
        sa.Column('is_completed', sa.Boolean, nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False),
    )
    op.create_index("ix_actions_user_id", 'actions', ['user_id'], unique=False)
    op.create_index("ix_actions_email_id", 'actions', ['email_id'], unique=False)
    op.create_table('reminders',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id'), nullable=False),
        sa.Column('email_id', sa.Integer, sa.ForeignKey('emails.id'), nullable=False),
        sa.Column('description', sa.String(512), nullable=True),
        sa.Column('deadline_at', sa.DateTime, nullable=False),
        sa.Column('is_dismissed', sa.Boolean, nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False),
    )
    op.create_index("ix_reminders_user_id", 'reminders', ['user_id'], unique=False)
    op.create_index("ix_reminders_email_id", 'reminders', ['email_id'], unique=False)
    op.create_index("ix_reminders_deadline_at", 'reminders', ['deadline_at'], unique=False)
    op.create_table('user_feedback',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id'), nullable=False),
        sa.Column('email_id', sa.Integer, sa.ForeignKey('emails.id'), nullable=False),
        sa.Column('feedback_type', sa.String(16), nullable=False),
        sa.Column('original_value', sa.String(32), nullable=True),
        sa.Column('corrected_value', sa.String(32), nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False),
    )
    op.create_index("ix_user_feedback_user_id", 'user_feedback', ['user_id'], unique=False)
    op.create_index("ix_user_feedback_email_id", 'user_feedback', ['email_id'], unique=False)


def downgrade():
    op.drop_table('user_feedback')
    op.drop_table('reminders')
    op.drop_table('actions')
    op.drop_table('emails')
    op.drop_table('users')
