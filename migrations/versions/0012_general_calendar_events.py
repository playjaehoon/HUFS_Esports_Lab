"""Allow general public schedules while retaining every existing event."""
from alembic import op
import sqlalchemy as sa

revision = '0012'
down_revision = '0011'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('calendar_event') as batch:
        batch.add_column(sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default='0'))
        batch.drop_constraint('calendar_kind', type_='check')
        batch.create_check_constraint('calendar_kind', "kind IN ('class','rental','event','general','closed')")


def downgrade():
    with op.batch_alter_table('calendar_event') as batch:
        batch.drop_column('is_deleted')
    op.execute("UPDATE calendar_event SET kind='event' WHERE kind='general'")
    with op.batch_alter_table('calendar_event') as batch:
        batch.drop_constraint('calendar_kind', type_='check')
        batch.create_check_constraint('calendar_kind', "kind IN ('class','rental','event','closed')")
