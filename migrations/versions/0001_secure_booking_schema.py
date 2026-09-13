"""Secure booking schema

Revision ID: 0001
Revises:
Create Date: 2026-09-14 00:57:57.351257

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # A legacy database must be imported into a separate file, never overwritten.
    if set(sa.inspect(op.get_bind()).get_table_names()) - {'alembic_version'}:
        raise RuntimeError('Existing database detected. Use import-legacy for the initial upgrade.')
    op.create_table('admin',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('username', sa.String(length=50), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('session_version', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('username')
    )
    op.create_table('audit_event',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('actor', sa.String(length=50), nullable=False),
    sa.Column('action', sa.String(length=50), nullable=False),
    sa.Column('target', sa.String(length=50), nullable=False),
    sa.Column('reason', sa.String(length=200), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('blocked_time',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('date', sa.String(length=10), nullable=False),
    sa.Column('start_time', sa.Integer(), nullable=True),
    sa.Column('end_time', sa.Integer(), nullable=True),
    sa.Column('seat_number', sa.Integer(), nullable=True),
    sa.Column('reason', sa.String(length=200), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('blocked_time', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_blocked_time_date'), ['date'], unique=False)

    op.create_table('login_attempt',
    sa.Column('key', sa.String(length=64), nullable=False),
    sa.Column('count', sa.Integer(), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('key')
    )
    with op.batch_alter_table('login_attempt', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_login_attempt_expires_at'), ['expires_at'], unique=False)

    op.create_table('setting',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('key', sa.String(length=50), nullable=False),
    sa.Column('value', sa.String(length=255), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('key')
    )
    op.create_table('student',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('student_number', sa.String(length=9), nullable=False),
    sa.Column('name', sa.String(length=50), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('blocked_until', sa.DateTime(), nullable=True),
    sa.Column('archived', sa.Boolean(), nullable=False),
    sa.Column('must_change_password', sa.Boolean(), nullable=False),
    sa.Column('session_version', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('student_number')
    )
    op.create_table('reservation',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('student_pk', sa.Integer(), nullable=False),
    sa.Column('student_id', sa.String(length=20), nullable=False),
    sa.Column('student_name', sa.String(length=50), nullable=False),
    sa.Column('date', sa.String(length=10), nullable=False),
    sa.Column('start_time', sa.Integer(), nullable=False),
    sa.Column('end_time', sa.Integer(), nullable=False),
    sa.Column('seat_number', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('is_attended', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('checked_in_at', sa.DateTime(), nullable=True),
    sa.Column('checked_in_by', sa.Integer(), nullable=True),
    sa.Column('checked_out_at', sa.DateTime(), nullable=True),
    sa.Column('checked_out_by', sa.Integer(), nullable=True),
    sa.Column('cancelled_at', sa.DateTime(), nullable=True),
    sa.CheckConstraint("status IN ('active','cancelled','completed','no_show')", name='reservation_status'),
    sa.CheckConstraint('seat_number > 0', name='reservation_positive_seat'),
    sa.CheckConstraint('start_time >= 0 AND end_time <= 24 AND start_time < end_time', name='reservation_time_range'),
    sa.ForeignKeyConstraint(['checked_in_by'], ['admin.id'], ),
    sa.ForeignKeyConstraint(['checked_out_by'], ['admin.id'], ),
    sa.ForeignKeyConstraint(['student_pk'], ['student.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('reservation', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_reservation_date'), ['date'], unique=False)
        batch_op.create_index(batch_op.f('ix_reservation_student_pk'), ['student_pk'], unique=False)

    op.create_table('daily_booking',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('student_pk', sa.Integer(), nullable=False),
    sa.Column('date', sa.String(length=10), nullable=False),
    sa.Column('reservation_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['reservation_id'], ['reservation.id'], ),
    sa.ForeignKeyConstraint(['student_pk'], ['student.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('reservation_id'),
    sa.UniqueConstraint('student_pk', 'date', name='unique_student_day')
    )
    op.create_table('reservation_slot',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('reservation_id', sa.Integer(), nullable=False),
    sa.Column('date', sa.String(length=10), nullable=False),
    sa.Column('seat_number', sa.Integer(), nullable=False),
    sa.Column('hour', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['reservation_id'], ['reservation.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('date', 'seat_number', 'hour', name='unique_seat_hour')
    )
    with op.batch_alter_table('reservation_slot', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_reservation_slot_reservation_id'), ['reservation_id'], unique=False)

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('reservation_slot', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_reservation_slot_reservation_id'))

    op.drop_table('reservation_slot')
    op.drop_table('daily_booking')
    with op.batch_alter_table('reservation', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_reservation_student_pk'))
        batch_op.drop_index(batch_op.f('ix_reservation_date'))

    op.drop_table('reservation')
    op.drop_table('student')
    op.drop_table('setting')
    with op.batch_alter_table('login_attempt', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_login_attempt_expires_at'))

    op.drop_table('login_attempt')
    with op.batch_alter_table('blocked_time', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_blocked_time_date'))

    op.drop_table('blocked_time')
    op.drop_table('audit_event')
    op.drop_table('admin')
    # ### end Alembic commands ###
