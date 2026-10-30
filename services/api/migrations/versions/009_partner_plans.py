"""Partner channel configuration and append-only validated quote revisions."""

from alembic import op
from sqlalchemy import select, func
from app.db.platform import Partner, CasePlan

revision = "009"
down_revision = "008"
branch_labels = depends_on = None


def upgrade():
    connection = op.get_bind()
    Partner.__table__.create(connection, checkfirst=True)
    CasePlan.__table__.create(connection, checkfirst=True)
    if connection.dialect.name == "postgresql":
        op.execute(
            "CREATE TRIGGER plans_append_only BEFORE UPDATE OR DELETE ON plans FOR EACH ROW EXECUTE FUNCTION helm_deny_mutation()"
        )
    else:
        for action in ("UPDATE", "DELETE"):
            op.execute(
                f"CREATE TRIGGER IF NOT EXISTS plans_no_{action.lower()} BEFORE {action} ON plans BEGIN SELECT RAISE(ABORT, 'Evidence records are append-only'); END"
            )


def downgrade():
    connection = op.get_bind()
    if connection.scalar(select(func.count()).select_from(CasePlan)):
        raise RuntimeError("Cannot downgrade persisted quotation evidence; restore a tested backup instead")
    CasePlan.__table__.drop(connection, checkfirst=True)
    Partner.__table__.drop(connection, checkfirst=True)
