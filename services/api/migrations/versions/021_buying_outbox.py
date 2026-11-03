"""Local-only confirmation messages, committed with demo issuance."""

from alembic import op
from app.db.policy_buying import BuyingDelivery

revision = "021"
down_revision = "020"
branch_labels = depends_on = None


def upgrade():
    connection = op.get_bind()
    BuyingDelivery.__table__.create(connection, checkfirst=True)
    if connection.dialect.name == "postgresql":
        op.execute(
            "CREATE TRIGGER pb_delivery_append_only BEFORE UPDATE OR DELETE ON pb_demo_deliveries FOR EACH ROW EXECUTE FUNCTION helm_deny_mutation()"
        )
    else:
        for action in ("UPDATE", "DELETE"):
            op.execute(
                f"CREATE TRIGGER IF NOT EXISTS pb_delivery_no_{action.lower()} BEFORE {action} ON pb_demo_deliveries BEGIN SELECT RAISE(ABORT, 'Evidence records are append-only'); END"
            )


def downgrade():
    raise RuntimeError("Demo delivery evidence must be preserved")
