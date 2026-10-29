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
        op.add_column("users", Column("is_lead_broker", Boolean, nullable=False, server_default=text("false")))
    Base.metadata.create_all(bind)


def downgrade():
    raise RuntimeError("Archive evidential records before destructive downgrade; use a disposable DB for migration tests")
