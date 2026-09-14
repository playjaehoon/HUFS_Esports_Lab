"""Persistence models. Timestamps are stored as naive UTC."""
from datetime import datetime, timezone
from uuid import uuid4
from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Admin(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    session_version = db.Column(db.Integer, nullable=False, default=1)

    def get_id(self):
        return f"admin_{self.id}_{self.session_version}"


class Student(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_number = db.Column(db.String(9), unique=True, nullable=False)
    name = db.Column(db.String(50), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    blocked_until = db.Column(db.DateTime)
    archived = db.Column(db.Boolean, nullable=False, default=False)
    must_change_password = db.Column(db.Boolean, nullable=False, default=False)
    session_version = db.Column(db.Integer, nullable=False, default=1)

    @property
    def is_active(self):
        return not self.archived

    def get_id(self):
        return f"student_{self.id}_{self.session_version}"


class Reservation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_pk = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False, index=True)
    # Historical identity snapshots; never use these for authorization.
    student_id = db.Column(db.String(20), nullable=False)
    student_name = db.Column(db.String(50), nullable=False)
    date = db.Column(db.String(10), nullable=False, index=True)
    start_minute = db.Column(db.Integer, nullable=False)
    end_minute = db.Column(db.Integer, nullable=False)
    seat_number = db.Column(db.Integer, nullable=False)
    booking_ip = db.Column(db.String(45))
    status = db.Column(db.String(20), nullable=False, default='active')
    is_attended = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    checked_in_at = db.Column(db.DateTime)
    checked_in_by = db.Column(db.Integer, db.ForeignKey('admin.id'))
    checked_out_at = db.Column(db.DateTime)
    checked_out_by = db.Column(db.Integer, db.ForeignKey('admin.id'))
    cancelled_at = db.Column(db.DateTime)
    student = db.relationship(Student)
    __table_args__ = (
        db.CheckConstraint('start_minute >= 0 AND end_minute <= 1440 AND start_minute < end_minute', name='reservation_time_range'),
        db.CheckConstraint('start_minute % 30 = 0 AND end_minute % 30 = 0', name='reservation_half_hour_grid'),
        db.CheckConstraint('seat_number > 0', name='reservation_positive_seat'),
        db.CheckConstraint("status IN ('active','cancelled','completed','no_show')", name='reservation_status'),
    )

    @property
    def state_label(self):
        return {'cancelled': '취소', 'completed': '이용 완료', 'no_show': '노쇼 확정'}.get(
            self.status, '이용 중' if self.is_attended else '예약 완료')


class StudentNumberClaim(db.Model):
    # Retain ownership of old numbers so profile edits cannot reset sanctions.
    student_number = db.Column(db.String(9), primary_key=True)
    student_pk = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False, index=True)


class ReservationSlot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    reservation_id = db.Column(db.Integer, db.ForeignKey('reservation.id'), nullable=False, index=True)
    date = db.Column(db.String(10), nullable=False)
    seat_number = db.Column(db.Integer, nullable=False)
    minute = db.Column(db.Integer, nullable=False)
    __table_args__ = (db.UniqueConstraint('date', 'seat_number', 'minute', name='unique_seat_minute'),)


class DailyBooking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_pk = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    date = db.Column(db.String(10), nullable=False)
    reservation_id = db.Column(db.Integer, db.ForeignKey('reservation.id'), nullable=False, unique=True)
    __table_args__ = (db.UniqueConstraint('student_pk', 'date', name='unique_student_day'),)


class BlockedTime(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(10), nullable=False, index=True)
    start_minute = db.Column(db.Integer)
    end_minute = db.Column(db.Integer)
    seat_number = db.Column(db.Integer)
    reason = db.Column(db.String(200), nullable=False, default='운영 일정')
    kind = db.Column(db.String(20), nullable=False, default='event')
    group_token = db.Column(db.String(36), nullable=False, default=lambda: uuid4().hex)
    __table_args__ = (
        db.CheckConstraint('(start_minute IS NULL AND end_minute IS NULL) OR '
                           '(start_minute >= 0 AND end_minute <= 1440 AND start_minute < end_minute)',
                           name='blocked_time_range'),
    )


class RecurringBlock(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    weekday = db.Column(db.Integer, nullable=False)
    start_minute = db.Column(db.Integer, nullable=False)
    end_minute = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(200), nullable=False)
    __table_args__ = (
        db.CheckConstraint('weekday >= 0 AND weekday <= 6', name='recurring_block_weekday'),
        db.CheckConstraint('start_minute >= 0 AND end_minute <= 1440 AND start_minute < end_minute',
                           name='recurring_block_range'),
        db.CheckConstraint('start_minute % 30 = 0 AND end_minute % 30 = 0',
                           name='recurring_block_half_hour_grid'),
    )


class Setting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.String(255), nullable=False)


class AuditEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    actor = db.Column(db.String(50), nullable=False)
    action = db.Column(db.String(50), nullable=False)
    target = db.Column(db.String(50), nullable=False)
    reason = db.Column(db.String(200), nullable=False, default='')
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class LoginAttempt(db.Model):
    key = db.Column(db.String(64), primary_key=True)
    count = db.Column(db.Integer, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False, index=True)
