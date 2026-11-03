"""AES-256-GCM encrypted demo banking responses."""

from alembic import op
from app.db.policy_buying import BuyingBanking

revision = "019"
down_revision = "018"
branch_labels = depends_on = None


def upgrade():
    BuyingBanking.__table__.create(op.get_bind(), checkfirst=True)


def downgrade():
    raise RuntimeError("Banking response evidence must be preserved")
