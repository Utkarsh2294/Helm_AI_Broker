from alembic import op
from sqlalchemy import Column, String, inspect

revision = "005"
down_revision = "004"
branch_labels = depends_on = None


def upgrade():
    if "priority" not in {c["name"] for c in inspect(op.get_bind()).get_columns("cases")}:
        op.add_column("cases", Column("priority", String(20), nullable=False, server_default="normal"))


def downgrade():
    # Keep this additive non-sensitive display field; evidence downgrades remain guarded.
    pass
