"""Governance evidence and a single database-enforced champion."""
from alembic import op
from app.db.platform import GovernanceEvent, EngineModel

revision = "003"
down_revision = "002"
branch_labels = depends_on = None


def upgrade():
    bind = op.get_bind()
    GovernanceEvent.__table__.create(bind, checkfirst=True)
    for index in EngineModel.__table__.indexes:
        index.create(bind, checkfirst=True)
    if bind.dialect.name == "postgresql":
        op.execute("CREATE TRIGGER governance_append_only BEFORE UPDATE OR DELETE ON governance_events FOR EACH ROW EXECUTE FUNCTION helm_deny_mutation()")


def downgrade():
    if op.get_bind().execute(GovernanceEvent.__table__.select().limit(1)).first():
        raise RuntimeError("Cannot downgrade populated governance evidence")
    GovernanceEvent.__table__.drop(op.get_bind())
    for index in EngineModel.__table__.indexes:
        index.drop(op.get_bind(), checkfirst=True)
