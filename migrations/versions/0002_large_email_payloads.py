"""Allow full-sized email bodies and Gmail payloads on MySQL."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import LONGTEXT

revision = "large_email_payloads"
down_revision = "phase11_baseline"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name == "mysql":
        for column in ("body", "raw_payload"):
            op.alter_column("emails", column, existing_type=sa.Text(),
                            type_=LONGTEXT(), existing_nullable=True)


def downgrade():
    if op.get_bind().dialect.name == "mysql":
        for column in ("body", "raw_payload"):
            op.alter_column("emails", column, existing_type=LONGTEXT(),
                            type_=sa.Text(), existing_nullable=True)
