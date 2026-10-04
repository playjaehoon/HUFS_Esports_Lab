"""Allow multiple post photos and opt-in sanitized HTML bodies."""
from alembic import op
import sqlalchemy as sa

revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('board_post') as batch:
        batch.add_column(sa.Column('body_format', sa.String(length=10), nullable=False, server_default='text'))
    op.create_table(
        'board_attachment',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('post_id', sa.Integer(), sa.ForeignKey('board_post.id', ondelete='CASCADE'), nullable=False),
        sa.Column('image_path', sa.String(length=200), nullable=False),
        sa.Column('image_alt', sa.String(length=160), nullable=False),
    )
    op.create_index('ix_board_attachment_post_id', 'board_attachment', ['post_id'])


def downgrade():
    op.drop_index('ix_board_attachment_post_id', table_name='board_attachment')
    op.drop_table('board_attachment')
    with op.batch_alter_table('board_post') as batch:
        batch.drop_column('body_format')
