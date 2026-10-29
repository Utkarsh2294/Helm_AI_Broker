"""Protect new approval, ingress and anchor evidence against direct SQL mutation."""
from alembic import op

revision = "004"
down_revision = "003"
branch_labels = depends_on = None
TABLES = ("governance_events", "model_approvals", "audit_anchors", "inbox_events")


def upgrade():
    bind = op.get_bind()
    for table in TABLES:
        if bind.dialect.name == "postgresql":
            op.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table}")
            if table == "governance_events":
                op.execute("DROP TRIGGER IF EXISTS governance_append_only ON governance_events")
            op.execute(f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION helm_deny_mutation()")
        else:
            for operation in ("UPDATE", "DELETE"):
                op.execute(f"CREATE TRIGGER IF NOT EXISTS {table}_no_{operation.lower()} BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT, 'Evidence records are append-only'); END")


def downgrade():
    for table in TABLES:
        if op.get_bind().dialect.name == "postgresql":
            op.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table}")
        else:
            for operation in ("update", "delete"):
                op.execute(f"DROP TRIGGER IF EXISTS {table}_no_{operation}")
