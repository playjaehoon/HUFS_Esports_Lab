"""Store the selected Global Campus department without changing legacy students."""

from alembic import op
import sqlalchemy as sa

revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('student') as batch:
        batch.add_column(sa.Column('department', sa.String(length=100), nullable=True))
    with op.batch_alter_table('setting') as batch:
        batch.alter_column('value', existing_type=sa.String(length=255), type_=sa.Text(), existing_nullable=False)


def downgrade():
    with op.batch_alter_table('setting') as batch:
        batch.alter_column('value', existing_type=sa.Text(), type_=sa.String(length=255), existing_nullable=False)
    with op.batch_alter_table('student') as batch:
        batch.drop_column('department')
