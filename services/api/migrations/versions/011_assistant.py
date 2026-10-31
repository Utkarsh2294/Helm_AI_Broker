"""Encrypted assistant history, temporary files and expiring reviewer links."""

from alembic import op
from sqlalchemy import select, func
from app.db.assistant import AssistantLog, AssistantFile, AssistantShare

revision = "011"
down_revision = "010"
branch_labels = depends_on = None


def upgrade():
    connection = op.get_bind()
    for model in (AssistantLog, AssistantFile, AssistantShare):
        model.__table__.create(connection, checkfirst=True)
    if connection.dialect.name == "postgresql":
        op.execute(
            "CREATE TRIGGER assistant_logs_append_only BEFORE UPDATE OR DELETE ON assistant_logs FOR EACH ROW EXECUTE FUNCTION helm_deny_mutation()"
        )
    else:
        for action in ("UPDATE", "DELETE"):
            op.execute(
                f"CREATE TRIGGER IF NOT EXISTS assistant_logs_no_{action.lower()} BEFORE {action} ON assistant_logs BEGIN SELECT RAISE(ABORT, 'Evidence records are append-only'); END"
            )


def downgrade():
    connection = op.get_bind()
    if connection.scalar(select(func.count()).select_from(AssistantLog)):
        raise RuntimeError("Cannot downgrade saved assistant evidence; restore a tested backup instead")
    for model in (AssistantShare, AssistantFile, AssistantLog):
        model.__table__.drop(connection, checkfirst=True)
