"""Persist image display widths without touching uploaded files or post content."""
from alembic import op
import sqlalchemy as sa

revision = '0013'
down_revision = '0012'
branch_labels = None
depends_on = None


def upgrade():
    # Add columns in place: rebuilding the parent would break existing attachment FKs.
    op.add_column('board_post', sa.Column('image_width', sa.Integer(),
        sa.CheckConstraint('image_width >= 25 AND image_width <= 100', name='board_image_width'),
        nullable=False, server_default='100'))
    op.add_column('board_attachment', sa.Column('display_width', sa.Integer(),
        sa.CheckConstraint('display_width >= 25 AND display_width <= 100', name='attachment_width'),
        nullable=False, server_default='100'))


def downgrade():
    # SQLite 3.35+ removes the column and its column-level constraint together.
    op.drop_column('board_attachment', 'display_width')
    op.drop_column('board_post', 'image_width')
