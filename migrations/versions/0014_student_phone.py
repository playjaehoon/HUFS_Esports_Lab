"""Add optional storage for existing members' contact numbers without rebuilding students."""
from alembic import op
import sqlalchemy as sa

revision = '0014'
down_revision = '0013'
branch_labels = None
depends_on = None


def upgrade():
    # Existing students stay NULL; do not invent contact data or rebuild FK parents.
    op.add_column('student', sa.Column('phone', sa.String(16), nullable=True))


def downgrade():
    op.drop_column('student', 'phone')
