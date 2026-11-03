"""Encrypted, append-only seeded FMU answers."""

from alembic import op
from app.db.policy_buying import BuyingMedicalResponse, drop_empty_table

revision = "018"
down_revision = "017"
branch_labels = depends_on = None


def upgrade():
    connection = op.get_bind()
    BuyingMedicalResponse.__table__.create(connection, checkfirst=True)
    if connection.dialect.name == "postgresql":
        op.execute(
            "CREATE TRIGGER pb_medical_append_only BEFORE UPDATE OR DELETE ON pb_medical_responses FOR EACH ROW EXECUTE FUNCTION helm_deny_mutation()"
        )
    else:
        for action in ("UPDATE", "DELETE"):
            op.execute(
                f"CREATE TRIGGER IF NOT EXISTS pb_medical_no_{action.lower()} BEFORE {action} ON pb_medical_responses BEGIN SELECT RAISE(ABORT, 'Evidence records are append-only'); END"
            )


def downgrade():
    drop_empty_table(op.get_bind(), BuyingMedicalResponse)
