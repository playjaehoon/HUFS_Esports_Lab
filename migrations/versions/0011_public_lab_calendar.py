"""Add public lab events without changing existing reservations or blocks."""
from alembic import op
import sqlalchemy as sa

revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('calendar_event',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('title', sa.String(100), nullable=False),
        sa.Column('kind', sa.String(12), nullable=False),
        sa.Column('start_date', sa.String(10), nullable=False),
        sa.Column('end_date', sa.String(10), nullable=False),
        sa.Column('weekday', sa.Integer()),
        sa.Column('start_minute', sa.Integer()),
        sa.Column('end_minute', sa.Integer()),
        sa.Column('blocks_reservations', sa.Boolean(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.CheckConstraint("kind IN ('class','rental','event','closed')", name='calendar_kind'),
        sa.CheckConstraint('start_date <= end_date', name='calendar_dates'),
        sa.CheckConstraint('weekday IS NULL OR (weekday >= 0 AND weekday <= 6)', name='calendar_weekday'),
        sa.CheckConstraint('(start_minute IS NULL AND end_minute IS NULL) OR '
                           '(start_minute >= 0 AND end_minute <= 1440 AND start_minute < end_minute '
                           'AND start_minute % 30 = 0 AND end_minute % 30 = 0)', name='calendar_time'))
    op.create_index('ix_calendar_event_start_date', 'calendar_event', ['start_date'])
    op.execute("INSERT INTO setting (key, value) SELECT 'open_weekdays', '[0,1,2,3,4]' "
               "WHERE NOT EXISTS (SELECT 1 FROM setting WHERE key='open_weekdays')")


def downgrade():
    op.drop_table('calendar_event')
