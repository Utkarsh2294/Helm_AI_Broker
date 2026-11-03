"""AES-256-GCM encrypted demo banking responses."""

from alembic import op
from app.db.policy_buying import BuyingBanking, drop_empty_table

revision = "019"
down_revision = "018"
branch_labels = depends_on = None


def upgrade():
    BuyingBanking.__table__.create(op.get_bind(), checkfirst=True)


def downgrade():
    drop_empty_table(op.get_bind(), BuyingBanking)
