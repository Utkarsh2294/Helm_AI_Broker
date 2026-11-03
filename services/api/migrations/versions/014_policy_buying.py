"""Independent demo policy-buying pipeline."""

from alembic import op
from sqlalchemy import select, func
from app.db.policy_buying import BuyingCase

revision = "014"
down_revision = "013"
branch_labels = depends_on = None


def upgrade():
    BuyingCase.__table__.create(op.get_bind(), checkfirst=True)


def downgrade():
    connection = op.get_bind()
    if connection.scalar(select(func.count()).select_from(BuyingCase)):
        raise RuntimeError("Preserve saved policy-buying evidence before downgrade")
    BuyingCase.__table__.drop(connection)
