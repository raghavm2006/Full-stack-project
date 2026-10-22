"""Store complete multi-recipient To headers without truncation."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import LONGTEXT

revision = "recipient_lists"
down_revision = "large_email_payloads"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("emails") as batch:
        batch.alter_column("receiver", existing_type=sa.String(320),
                           type_=sa.Text().with_variant(LONGTEXT(), "mysql"),
                           existing_nullable=True)


def downgrade():
    with op.batch_alter_table("emails") as batch:
        batch.alter_column("receiver",
                           existing_type=sa.Text().with_variant(LONGTEXT(), "mysql"),
                           type_=sa.String(320), existing_nullable=True)
