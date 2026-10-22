"""Allow users to opt into sender-specific correction rules."""
from alembic import op
import sqlalchemy as sa

revision = "sender_feedback"
down_revision = "recipient_lists"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("user_feedback") as batch:
        batch.add_column(sa.Column("apply_to_sender", sa.Boolean(), nullable=False,
                                   server_default=sa.false()))


def downgrade():
    with op.batch_alter_table("user_feedback") as batch:
        batch.drop_column("apply_to_sender")
