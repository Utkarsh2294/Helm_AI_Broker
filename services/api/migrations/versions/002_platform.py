"""Add complete-prototype auth, integration and governance records without deleting evidence."""

from alembic import op
from sqlalchemy import Boolean, Column, String, inspect, text
from app.db.models import Base

revision = "002"
down_revision = "001"


def upgrade():
    bind = op.get_bind()
    columns = {c["name"] for c in inspect(bind).get_columns("users")}
    if "fca_irn" not in columns:
        op.add_column("users", Column("fca_irn", String(100), nullable=True))
    if "is_lead_broker" not in columns:
        op.add_column(
            "users", Column("is_lead_broker", Boolean, nullable=False, server_default=text("false"))
        )
    Base.metadata.create_all(bind)


def downgrade():
    from sqlalchemy import func, select

    legacy = {
        "users",
        "sessions",
        "cases",
        "snapshots",
        "approvals",
        "activity_events",
        "jobs",
        "model_change_requests",
        "publications",
    }
    bind = op.get_bind()
    existing_tables = set(inspect(bind).get_table_names())
    for table in reversed(Base.metadata.sorted_tables):
        if table.name not in legacy and table.name in existing_tables:
            if bind.scalar(select(func.count()).select_from(table)):
                raise RuntimeError("Archive prototype records before destructive downgrade")
            table.drop(bind, checkfirst=True)
