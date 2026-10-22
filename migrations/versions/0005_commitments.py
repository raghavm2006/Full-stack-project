"""Add independently confirmed conversation commitments."""
from alembic import op
import sqlalchemy as sa

revision = "commitments"
down_revision = "sender_feedback"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("commitments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("source_email_id", sa.Integer(), sa.ForeignKey("emails.id"), nullable=False),
        sa.Column("thread_id", sa.String(64), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=False),
        sa.Column("responsible", sa.String(16), nullable=False),
        sa.Column("deadline_at", sa.DateTime(), nullable=True),
        sa.Column("deadline_note", sa.String(255), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("is_change", sa.Boolean(), nullable=False),
        sa.Column("supersedes_id", sa.Integer(), sa.ForeignKey("commitments.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("user_id", "source_email_id", "fingerprint", name="uq_commitment_source"))
    op.create_index("ix_commitments_user_id", "commitments", ["user_id"])
    op.create_index("ix_commitments_thread_id", "commitments", ["thread_id"])


def downgrade():
    op.drop_table("commitments")
