"""Delivery markers and scoped assistant parse-cache lookup keys."""

from alembic import op
from sqlalchemy import inspect, Column, String

revision = "013"
down_revision = "012"
branch_labels = depends_on = None


def upgrade():
    connection = op.get_bind()
    for table, fields in [
        ("notifications", [("push_sent_at", 40)]),
        ("assistant_files", [("cache_key", 64)]),
    ]:
        existing = {column["name"] for column in inspect(connection).get_columns(table)}
        for name, length in fields:
            if name not in existing:
                op.add_column(table, Column(name, String(length), nullable=True))
    indexes = {index["name"] for index in inspect(connection).get_indexes("assistant_files")}
    if "ix_assistant_files_cache_key" not in indexes:
        op.create_index("ix_assistant_files_cache_key", "assistant_files", ["cache_key"], unique=True)


def downgrade():
    # These nullable operational columns are safe to leave for an older application.
    pass
