"""Standing per-consumer demo terms acknowledgements."""

from alembic import op
from app.db.policy_buying import BuyingAgreement

revision = "017"
down_revision = "016"
branch_labels = depends_on = None


def upgrade():
    connection = op.get_bind()
    BuyingAgreement.__table__.create(connection, checkfirst=True)
    if connection.dialect.name == "postgresql":
        op.execute(
            "CREATE TRIGGER pb_agreements_append_only BEFORE UPDATE OR DELETE ON pb_standing_agreements FOR EACH ROW EXECUTE FUNCTION helm_deny_mutation()"
        )
    else:
        for action in ("UPDATE", "DELETE"):
            op.execute(
                f"CREATE TRIGGER IF NOT EXISTS pb_agreements_no_{action.lower()} BEFORE {action} ON pb_standing_agreements BEGIN SELECT RAISE(ABORT, 'Evidence records are append-only'); END"
            )


def downgrade():
    raise RuntimeError("Standing agreement evidence must be preserved")
