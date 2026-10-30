"""Immutable, ranking-bound versions of every broker's plan assessment."""

from alembic import op
from sqlalchemy import select, func
from app.db.platform import BrokerRating

revision = "010"
down_revision = "009"
branch_labels = depends_on = None


def upgrade():
    connection = op.get_bind()
    BrokerRating.__table__.create(connection, checkfirst=True)
    if connection.dialect.name == "postgresql":
        op.execute(
            "CREATE TRIGGER broker_ratings_append_only BEFORE UPDATE OR DELETE ON broker_ratings FOR EACH ROW EXECUTE FUNCTION helm_deny_mutation()"
        )
    else:
        for action in ("UPDATE", "DELETE"):
            op.execute(
                f"CREATE TRIGGER IF NOT EXISTS broker_ratings_no_{action.lower()} BEFORE {action} ON broker_ratings BEGIN SELECT RAISE(ABORT, 'Evidence records are append-only'); END"
            )


def downgrade():
    connection = op.get_bind()
    if connection.scalar(select(func.count()).select_from(BrokerRating)):
        raise RuntimeError("Cannot downgrade saved broker assessments; restore a tested backup instead")
    BrokerRating.__table__.drop(connection, checkfirst=True)
