"""Allow one-time reveal markers but forbid changing saved banking responses."""

from alembic import op

revision = "020"
down_revision = "019"
branch_labels = depends_on = None


def upgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "CREATE TRIGGER pb_banking_no_body_update BEFORE UPDATE OF body ON pb_banking_details FOR EACH ROW EXECUTE FUNCTION helm_deny_mutation()"
        )
        op.execute(
            "CREATE TRIGGER pb_banking_no_delete BEFORE DELETE ON pb_banking_details FOR EACH ROW EXECUTE FUNCTION helm_deny_mutation()"
        )
    else:
        op.execute(
            "CREATE TRIGGER IF NOT EXISTS pb_banking_no_body_update BEFORE UPDATE OF body ON pb_banking_details BEGIN SELECT RAISE(ABORT, 'Banking answers are immutable'); END"
        )
        op.execute(
            "CREATE TRIGGER IF NOT EXISTS pb_banking_no_delete BEFORE DELETE ON pb_banking_details BEGIN SELECT RAISE(ABORT, 'Banking answers are immutable'); END"
        )


def downgrade():
    from sqlalchemy import select, func
    from app.db.policy_buying import BuyingBanking

    connection = op.get_bind()
    if connection.scalar(select(func.count()).select_from(BuyingBanking)):
        raise RuntimeError("Banking table contains user or evidence records; preserve its protections")
    for name in ("pb_banking_no_body_update", "pb_banking_no_delete"):
        suffix = " ON pb_banking_details" if connection.dialect.name == "postgresql" else ""
        op.execute(f"DROP TRIGGER IF EXISTS {name}{suffix}")
