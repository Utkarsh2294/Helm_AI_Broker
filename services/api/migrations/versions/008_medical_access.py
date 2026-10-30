"""Session/case-bound, expiring medical access grants."""

from alembic import op
from app.db.platform import MedicalAccess

revision = "008"
down_revision = "007"
branch_labels = depends_on = None


def upgrade():
    MedicalAccess.__table__.create(op.get_bind(), checkfirst=True)


def downgrade():
    # Session grants contain no medical text and expire; retain for safe rollback.
    pass
