"""Initial encrypted workflow schema, including immutable evidence triggers."""
from alembic import op
from app.db.models import Base

revision = "001"
down_revision = None


def upgrade():
    bind = op.get_bind()
    Base.metadata.create_all(bind)
    evidential = ("snapshots", "approvals", "activity_events", "publications")
    if bind.dialect.name == "postgresql":
        op.execute("""CREATE FUNCTION helm_deny_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
                   BEGIN RAISE EXCEPTION 'Evidence records are append-only'; END; $$""")
        for table in evidential:
            op.execute(f"CREATE TRIGGER immutable_{table} BEFORE UPDATE OR DELETE ON {table} "
                       "FOR EACH ROW EXECUTE FUNCTION helm_deny_mutation()")
    elif bind.dialect.name == "sqlite":
        for table in evidential:
            for action in ("UPDATE", "DELETE"):
                op.execute(f"CREATE TRIGGER immutable_{table}_{action} BEFORE {action} ON {table} "
                           "BEGIN SELECT RAISE(ABORT, 'Evidence records are append-only'); END")


def downgrade():
    raise RuntimeError("Evidence retention requires an explicit archival procedure; destructive downgrade disabled")
