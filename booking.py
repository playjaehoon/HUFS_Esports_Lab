"""Shared validation and transactional booking operations for SQLite."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import re
from zoneinfo import ZoneInfo
from flask import current_app
from sqlalchemy import text
from models import AuditEvent, BlockedTime, DailyBooking, ReservationSlot, Setting, db, utcnow

KOREA = ZoneInfo('Asia/Seoul')
SEATS = tuple(range(1, 28))  # Existing drawing; confirm onsite before deployment.
DEFAULTS = {'reservation_open': '1', 'max_hours': '3', 'open_hour': '9', 'close_hour': '17',
            'advance_days': '7', 'notice': '이용 당일 학생증을 준비해 주세요.'}


class RuleError(ValueError):
    def __init__(self, message, status=400):
        self.status = status
        super().__init__(message)


def korea_now():
    clock = current_app.config.get('NOW_PROVIDER')
    return (clock() if clock else datetime.now(timezone.utc)).astimezone(KOREA)


def rules():
    values = dict(DEFAULTS)
    values.update({s.key: s.value for s in db.session.scalars(db.select(Setting))})
    for key in ('max_hours', 'open_hour', 'close_hour', 'advance_days'):
        values[key] = int(values[key])
    return values


def integer(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, str)) or not re.fullmatch(r'[0-9]{1,3}', str(value)):
        raise RuleError(f'{label}을 올바르게 입력해 주세요.')
    return int(value)


def parse_date(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value):
        raise RuleError('예약 날짜를 확인해 주세요.')
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except ValueError:
        raise RuleError('존재하지 않는 날짜입니다.') from None


def booking_input(data, seat_required=True):
    if not isinstance(data, dict):
        raise RuleError('예약 정보를 확인해 주세요.')
    date = parse_date(data.get('date'))
    start, end = integer(data.get('start_time'), '시작 시간'), integer(data.get('end_time'), '종료 시간')
    policy = rules()
    now = korea_now()
    if not now.date() <= date <= now.date() + timedelta(days=policy['advance_days']):
        raise RuleError('예약 가능한 날짜 범위를 벗어났습니다.')
    if not policy['open_hour'] <= start < end <= policy['close_hour']:
        raise RuleError('운영시간 안에서 시작·종료 시간을 선택해 주세요.')
    if end - start > policy['max_hours']:
        raise RuleError(f"최대 {policy['max_hours']}시간까지 예약할 수 있습니다.")
    if datetime.combine(date, datetime.min.time(), KOREA) + timedelta(hours=start) <= now:
        raise RuleError('이미 시작된 시간은 예약할 수 없습니다.')
    seat = integer(data.get('seat_number'), '좌석 번호') if seat_required else None
    if seat_required and seat not in SEATS:
        raise RuleError('존재하지 않는 좌석입니다.')
    if policy['reservation_open'] != '1':
        raise RuleError('현재 예약 접수가 중지되어 있습니다.', 409)
    return date.isoformat(), start, end, seat


def blocked_seats(date, start, end):
    seats = set()
    for block in db.session.scalars(db.select(BlockedTime).where(BlockedTime.date == date)):
        if block.start_time is None or max(start, block.start_time) < min(end, block.end_time):
            seats.update(SEATS if block.seat_number is None else [block.seat_number])
    return seats


def allowed_student(student):
    if student.archived or (student.blocked_until and student.blocked_until > utcnow()):
        raise RuleError('이용이 제한된 계정입니다. 운영진에게 문의해 주세요.', 403)


@contextmanager
def write_transaction():
    # End read transactions from session loading, then serialize validation+writes.
    db.session.rollback()
    db.session.execute(text('BEGIN IMMEDIATE'))
    try:
        yield
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise


def event(actor, action, target, reason=''):
    db.session.add(AuditEvent(actor=actor, action=action, target=str(target), reason=reason[:200]))


def release(reservation):
    db.session.execute(db.delete(ReservationSlot).where(ReservationSlot.reservation_id == reservation.id))
    db.session.execute(db.delete(DailyBooking).where(DailyBooking.reservation_id == reservation.id))


def starts_at(reservation):
    return datetime.combine(parse_date(reservation.date), datetime.min.time(), KOREA) + timedelta(hours=reservation.start_time)


def ends_at(reservation):
    return starts_at(reservation) + timedelta(hours=reservation.end_time - reservation.start_time)
