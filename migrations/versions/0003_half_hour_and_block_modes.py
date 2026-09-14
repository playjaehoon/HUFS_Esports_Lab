"""Half-hour bookings and explicit blocking modes."""
from alembic import op
import sqlalchemy as sa

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('reservation') as batch:
        batch.drop_constraint('reservation_time_range', type_='check')
        batch.alter_column('start_time', new_column_name='start_minute')
        batch.alter_column('end_time', new_column_name='end_minute')
    op.execute('UPDATE reservation SET start_minute = start_minute * 60, end_minute = end_minute * 60')
    with op.batch_alter_table('reservation') as batch:
        batch.create_check_constraint('reservation_time_range', 'start_minute >= 0 AND end_minute <= 1440 AND start_minute < end_minute')
        batch.create_check_constraint('reservation_half_hour_grid', 'start_minute % 30 = 0 AND end_minute % 30 = 0')

    with op.batch_alter_table('reservation_slot') as batch:
        batch.drop_constraint('unique_seat_hour', type_='unique')
        batch.alter_column('hour', new_column_name='minute')
        batch.create_unique_constraint('unique_seat_minute', ['date', 'seat_number', 'minute'])
    op.execute('UPDATE reservation_slot SET minute = minute * 60')
    op.execute('''INSERT INTO reservation_slot (reservation_id, date, seat_number, minute)
                  SELECT reservation_id, date, seat_number, minute + 30 FROM reservation_slot''')

    with op.batch_alter_table('blocked_time') as batch:
        batch.alter_column('start_time', new_column_name='start_minute')
        batch.alter_column('end_time', new_column_name='end_minute')
        batch.add_column(sa.Column('kind', sa.String(length=20), nullable=True))
        batch.add_column(sa.Column('group_token', sa.String(length=36), nullable=True))
    op.execute('UPDATE blocked_time SET start_minute=start_minute*60, end_minute=end_minute*60 WHERE start_minute IS NOT NULL')
    op.execute("UPDATE blocked_time SET kind='event', group_token='legacy-' || id")
    with op.batch_alter_table('blocked_time') as batch:
        batch.alter_column('kind', existing_type=sa.String(length=20), nullable=False)
        batch.alter_column('group_token', existing_type=sa.String(length=36), nullable=False)
        batch.create_check_constraint('blocked_time_range', '(start_minute IS NULL AND end_minute IS NULL) OR (start_minute >= 0 AND end_minute <= 1440 AND start_minute < end_minute)')

    op.create_table('recurring_block',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('weekday', sa.Integer(), nullable=False),
        sa.Column('start_minute', sa.Integer(), nullable=False),
        sa.Column('end_minute', sa.Integer(), nullable=False),
        sa.Column('reason', sa.String(length=200), nullable=False),
        sa.CheckConstraint('weekday >= 0 AND weekday <= 6', name='recurring_block_weekday'),
        sa.CheckConstraint('start_minute >= 0 AND end_minute <= 1440 AND start_minute < end_minute', name='recurring_block_range'),
        sa.CheckConstraint('start_minute % 30 = 0 AND end_minute % 30 = 0', name='recurring_block_half_hour_grid'),
        sa.PrimaryKeyConstraint('id'))


def downgrade():
    connection = op.get_bind()
    if connection.execute(sa.text('SELECT count(*) FROM recurring_block')).scalar():
        raise RuntimeError('Remove recurring blocks before downgrading.')
    if connection.execute(sa.text('SELECT count(*) FROM reservation WHERE start_minute % 60 != 0 OR end_minute % 60 != 0')).scalar():
        raise RuntimeError('Half-hour reservations cannot be downgraded without data loss.')
    if connection.execute(sa.text('SELECT count(*) FROM blocked_time WHERE start_minute % 60 != 0 OR end_minute % 60 != 0')).scalar():
        raise RuntimeError('Half-hour blocks cannot be downgraded without data loss.')
    op.drop_table('recurring_block')
    with op.batch_alter_table('blocked_time') as batch:
        batch.drop_constraint('blocked_time_range', type_='check')
        batch.drop_column('group_token')
        batch.drop_column('kind')
        batch.alter_column('start_minute', new_column_name='start_time')
        batch.alter_column('end_minute', new_column_name='end_time')
    op.execute('UPDATE blocked_time SET start_time=start_time/60, end_time=end_time/60 WHERE start_time IS NOT NULL')
    op.execute('DELETE FROM reservation_slot WHERE minute % 60 != 0')
    with op.batch_alter_table('reservation_slot') as batch:
        batch.drop_constraint('unique_seat_minute', type_='unique')
        batch.alter_column('minute', new_column_name='hour')
        batch.create_unique_constraint('unique_seat_hour', ['date', 'seat_number', 'hour'])
    op.execute('UPDATE reservation_slot SET hour=hour/60')
    with op.batch_alter_table('reservation') as batch:
        batch.drop_constraint('reservation_time_range', type_='check')
        batch.drop_constraint('reservation_half_hour_grid', type_='check')
        batch.alter_column('start_minute', new_column_name='start_time')
        batch.alter_column('end_minute', new_column_name='end_time')
    op.execute('UPDATE reservation SET start_time=start_time/60, end_time=end_time/60')
    with op.batch_alter_table('reservation') as batch:
        batch.create_check_constraint('reservation_time_range', 'start_time >= 0 AND end_time <= 24 AND start_time < end_time')
