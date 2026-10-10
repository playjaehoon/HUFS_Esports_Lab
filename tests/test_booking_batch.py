"""Many real reservation requests against one isolated database, including blocks."""
import os
from pathlib import Path
import sqlite3

from sqlalchemy import func
from conftest import PASSWORD, booking, login, post, reserve
from models import BlockedTime, Reservation, ReservationSlot, Student, StudentNumberClaim, db


def test_many_bookings_blocks_recovery_and_allocation_integrity(app, password_hash):
    with app.app_context():
        for identifier in range(3, 31):
            db.session.add(Student(id=identifier, student_number=f'2026{identifier:05d}',
                                   name=f'예약 검수용 학생 {identifier:02d}',
                                   department='철학과' if identifier == 28 else '글로벌스포츠산업학부',
                                   password_hash=password_hash))
        db.session.flush()
        for identifier in range(3, 31):
            student = db.session.get(Student, identifier)
            db.session.add(StudentNumberClaim(student_number=student.student_number, student_pk=identifier))
        db.session.commit()

    # Use the usual CSRF-protected authentication and booking endpoints.
    clients = {}
    for identifier in range(1, 31):
        client = app.test_client()
        number = f'2026{identifier:05d}'
        assert post(client, '/login', {'student_number': number, 'password': PASSWORD}).status_code == 302
        clients[identifier] = client
    admin = login(app, admin=True)
    dates = ['2026-09-15', '2026-09-16', '2026-09-17']
    partial = {'start_date': dates[0], 'end_date': dates[-1], 'block_type': 'all',
               'seat_numbers': ['25', '26'], 'reason': '검수용 여러 날짜 좌석 점검'}
    assert post(admin, '/admin/block/seats', partial).status_code == 302
    with app.app_context():
        group_id = db.session.scalar(db.select(BlockedTime.id).order_by(BlockedTime.id))
        assert db.session.scalar(db.select(func.count()).select_from(BlockedTime)) == 6

    for day in dates:
        for identifier in range(1, 25):
            start = 540 + (identifier % 4) * 30
            end = start + (identifier % 3 + 1) * 30
            reserve(clients[identifier], date=day, seat_number=identifier,
                    start_time=f'{start // 60:02d}:{start % 60:02d}',
                    end_time=f'{end // 60:02d}:{end % 60:02d}')
        # An occupied seat, blocked seats, and a second daily booking stay unavailable.
        data = booking(date=day, start_time='09:30', end_time='10:00')
        availability = clients[25].get('/api/availability', query_string=data).get_json()
        assert 1 in availability['occupied_seats']
        assert {25, 26} <= set(availability['blocked_seats'])
        for seat in [1, 25, 26]:
            assert post(clients[25], '/api/reserve', json={**data, 'seat_number': seat}).status_code == 409
        assert post(clients[1], '/api/reserve', json={**data, 'seat_number': 27}).status_code == 409

    # Blocking existing reservations must fail atomically, without damaging bookings.
    assert post(admin, '/admin/block/seats', {**partial, 'seat_numbers': ['24', '27']}).status_code == 409
    with app.app_context():
        assert db.session.scalar(db.select(func.count()).select_from(BlockedTime)) == 6
        assert db.session.scalar(db.select(func.count()).select_from(Reservation)) == 72
    assert post(admin, f'/admin/unblock/{group_id}').status_code == 302
    for day in dates:
        assert 25 not in clients[25].get('/api/availability', query_string=booking(date=day)).get_json()['blocked_seats']

    # Cancel and reuse the same slot, then reserve the adjoining half hour.
    cancelled = reserve(clients[25], seat_number=25, start_time='09:00', end_time='09:30')
    assert post(clients[25], f'/my/reservations/{cancelled}/cancel').status_code == 302
    reserve(clients[26], seat_number=25, start_time='09:00', end_time='09:30')
    reserve(clients[27], seat_number=25, start_time='09:30', end_time='10:00')

    event = {'date': '2026-09-18', 'block_type': 'specific', 'start_time': '14:00',
             'end_time': '15:00', 'reason': '검수용 전체 대관'}
    assert post(admin, '/admin/block/event', event).status_code == 302
    room = booking(date=event['date'], start_time='14:00', end_time='14:30', seat_number=27)
    assert len(clients[29].get('/api/availability', query_string=room).get_json()['blocked_seats']) == 27
    assert post(clients[29], '/api/reserve', json=room).status_code == 409
    recurring = {'weekday': '3', 'start_time': '15:00', 'end_time': '16:00', 'reason': '검수용 정기 수업'}
    assert post(admin, '/admin/block/recurring', recurring).status_code == 302
    assert post(clients[29], '/api/reserve', json=booking(date=dates[-1], start_time='15:00', end_time='15:30')).status_code == 409

    assert post(admin, '/admin/departments', {'mode': 'allowlist', 'departments': ['글로벌스포츠산업학부']}).status_code == 302
    assert post(clients[28], '/api/reserve', json=booking(date='2026-09-18', seat_number=27)).status_code == 403
    assert post(admin, '/admin/departments', {'mode': 'all'}).status_code == 302
    reserve(clients[28], date='2026-09-18', seat_number=27)

    with app.app_context():
        reservations = db.session.scalars(db.select(Reservation)).all()
        slots = db.session.scalars(db.select(ReservationSlot)).all()
        assert len(reservations) == 76
        assert sum(row.status == 'active' for row in reservations) == 75
        assert len({(slot.date, slot.seat_number, slot.minute) for slot in slots}) == len(slots)
        for row in reservations:
            actual = {slot.minute for slot in slots if slot.reservation_id == row.id}
            assert actual == (set(range(row.start_minute, row.end_minute, 30)) if row.status == 'active' else set())
        source = Path(db.engine.url.database)
    with sqlite3.connect(source) as connection:
        assert connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert not connection.execute('PRAGMA foreign_key_check').fetchall()
        # Explicit opt-in export for a local UI review; normal tests leave the repo untouched.
        export = os.environ.get('BOOKING_REVIEW_EXPORT')
        if export:
            destination = Path(export)
            assert not destination.exists()
            with sqlite3.connect(destination) as snapshot:
                connection.backup(snapshot)
    assert admin.get('/admin?date=2026-09-15').status_code == 200
    assert admin.get('/admin?date=2026-09-18').status_code == 200
