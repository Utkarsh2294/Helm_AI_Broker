"""Add account-level lock state while preserving existing users and sessions."""

from alembic import op
from sqlalchemy import Boolean, Column, Integer, String, inspect, text
from app.db.platform import LoginAttempt

revision = "007"
down_revision = "006"
branch_labels = depends_on = None


def upgrade():
    bind = op.get_bind()
    columns = {column["name"] for column in inspect(bind).get_columns("users")}
    for name, kind, default in (
        ("is_active", Boolean, text("true")),
        ("failed_login_count", Integer, text("0")),
        ("locked_until", String(40), None),
    ):
        if name not in columns:
            op.add_column(
                "users", Column(name, kind, nullable=name == "locked_until", server_default=default)
            )
    LoginAttempt.__table__.create(bind, checkfirst=True)


def downgrade():
    # Authentication records and existing user columns survive a non-destructive rollback.
    pass
