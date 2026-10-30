"""Enable the main plan's PostgreSQL primitives without changing encrypted evidence."""

from alembic import op

revision = "006"
down_revision = "005"
branch_labels = depends_on = None


def upgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
        op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')


def downgrade():
    # Extensions may be shared by retained records or another application; keep them.
    pass
