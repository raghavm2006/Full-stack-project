"""Opt-in sending permissions and reviewed outgoing messages."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import LONGTEXT

revision = "outgoing_mail"
down_revision = "commitments"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("gmail_send_granted", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("gmail_drafts_granted", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table("outgoing_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reply_email_id", sa.Integer(), sa.ForeignKey("emails.id"), nullable=True),
        sa.Column("recipients", sa.Text(), nullable=False),
        sa.Column("cc", sa.Text(), nullable=False), sa.Column("bcc", sa.Text(), nullable=False),
        sa.Column("subject", sa.String(998), nullable=False),
        sa.Column("body", sa.Text().with_variant(LONGTEXT(), "mysql"), nullable=False),
        sa.Column("raw_message", sa.Text().with_variant(LONGTEXT(), "mysql"), nullable=False),
        sa.Column("attachments", sa.Text(), nullable=False), sa.Column("thread_id", sa.String(64)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("gmail_message_id", sa.String(64)), sa.Column("gmail_draft_id", sa.String(64)),
        sa.Column("created_at", sa.DateTime(), nullable=False))
    op.create_index("ix_outgoing_messages_user_id", "outgoing_messages", ["user_id"])


def downgrade():
    op.drop_table("outgoing_messages")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("gmail_send_granted")
        batch.drop_column("gmail_drafts_granted")
