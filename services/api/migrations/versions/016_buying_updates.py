"""Per-case append-only update feed and broker read positions."""

from alembic import op
from app.db.policy_buying import BuyingRead, BuyingUpdate

revision = "016"
down_revision = "015"
branch_labels = depends_on = None


def upgrade():
    connection = op.get_bind()
    for model in (BuyingUpdate, BuyingRead):
        model.__table__.create(connection, checkfirst=True)
    if connection.dialect.name == "postgresql":
        op.execute(
            "CREATE TRIGGER pb_update_feed_append_only BEFORE UPDATE OR DELETE ON pb_update_feed FOR EACH ROW EXECUTE FUNCTION helm_deny_mutation()"
        )
    else:
        for action in ("UPDATE", "DELETE"):
            op.execute(
                f"CREATE TRIGGER IF NOT EXISTS pb_update_feed_no_{action.lower()} BEFORE {action} ON pb_update_feed BEGIN SELECT RAISE(ABORT, 'Evidence records are append-only'); END"
            )


def downgrade():
    raise RuntimeError("Policy-buying communication evidence must be preserved")
