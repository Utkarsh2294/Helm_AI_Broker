"""Append-only, encrypted buying document versions."""

from alembic import op
from app.db.policy_buying import BuyingDocument

revision = "015"
down_revision = "014"
branch_labels = depends_on = None


def protect_table(connection, name):
    if connection.dialect.name == "postgresql":
        op.execute(
            f"CREATE TRIGGER {name}_append_only BEFORE UPDATE OR DELETE ON {name} FOR EACH ROW EXECUTE FUNCTION helm_deny_mutation()"
        )
    else:
        for action in ("UPDATE", "DELETE"):
            op.execute(
                f"CREATE TRIGGER IF NOT EXISTS {name}_no_{action.lower()} BEFORE {action} ON {name} BEGIN SELECT RAISE(ABORT, 'Evidence records are append-only'); END"
            )


def upgrade():
    connection = op.get_bind()
    BuyingDocument.__table__.create(connection, checkfirst=True)
    protect_table(connection, "pb_documents")


def downgrade():
    raise RuntimeError("Buying document evidence must be preserved; restore a tested backup")
