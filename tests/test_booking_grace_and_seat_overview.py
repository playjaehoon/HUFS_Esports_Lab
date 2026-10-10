from datetime import datetime
from zoneinfo import ZoneInfo
import pytest
from conftest import booking, login, post, reserve
from models import BlockedTime, RecurringBlock, Reservation, ReservationSlot, db


@pytest.mark.parametrize('hour,minute,second,allowed', [
    (15, 59, 59, True), (16, 0, 0, True), (16, 4, 59, True),
    (16, 5, 0, True), (16, 5, 1, False), (16, 6, 0, False),
])
def test_booking_grace_boundary_matches_availability_and_reservation(app, hour, minute, second, allowed):
    student = login(app)
    app.config['NOW_PROVIDER'] = lambda: datetime(2026, 9, 14, hour, minute, second, tzinfo=ZoneInfo('Asia/Seoul'))
    data = booking(date='2026-09-14', start_time='16:00', end_time='17:00')
    response = student.get('/api/availability', query_string=data)
    assert response.status_code == (200 if allowed else 400)
    result = post(student, '/api/reserve', json=data)
    assert result.status_code == (201 if allowed else 400)
    with app.app_context():
        rows = db.session.scalars(db.select(Reservation)).all()
        assert len(rows) == int(allowed)
        if allowed:
            assert rows[0].start_minute == 960 and rows[0].end_minute == 1020
            assert db.session.scalars(db.select(ReservationSlot.minute).order_by(ReservationSlot.minute)).all() == [960, 990]


def test_grace_keeps_occupied_and_blocked_seats_unavailable(app):
    first, second, admin = login(app), login(app, student=2), login(app, admin=True)
    reserve(first, date='2026-09-14', start_time='16:00', end_time='17:00')
    assert post(admin, '/admin/block/seats', {'start_date': '2026-09-14', 'end_date': '2026-09-14',
                'block_type': 'all', 'seat_numbers': ['2'], 'reason': 'Test maintenance'}).status_code == 302
    app.config['NOW_PROVIDER'] = lambda: datetime(2026, 9, 14, 16, 4, tzinfo=ZoneInfo('Asia/Seoul'))
    data = booking(date='2026-09-14', start_time='16:00', end_time='17:00')
    availability = second.get('/api/availability', query_string=data).get_json()
    assert 1 in availability['occupied_seats'] and 2 in availability['blocked_seats']
    assert post(second, '/api/reserve', json=data).status_code == 409
    assert post(second, '/api/reserve', json={**data, 'seat_number': 2}).status_code == 409
    assert post(second, '/api/reserve', json={**data, 'seat_number': 3}).status_code == 201


def test_deadline_is_rechecked_on_final_submit_and_yesterday_stays_blocked(app):
    student = login(app)
    data = booking(date='2026-09-14', start_time='16:00', end_time='17:00')
    app.config['NOW_PROVIDER'] = lambda: datetime(2026, 9, 14, 16, 4, tzinfo=ZoneInfo('Asia/Seoul'))
    assert student.get('/api/availability', query_string=data).status_code == 200
    app.config['NOW_PROVIDER'] = lambda: datetime(2026, 9, 14, 16, 6, tzinfo=ZoneInfo('Asia/Seoul'))
    assert post(student, '/api/reserve', json=data).status_code == 400
    assert post(student, '/api/reserve', json={**data, 'date': '2026-09-13'}).status_code == 400


def test_admin_seat_overview_is_complete_with_search_and_date_scoped(app):
    first, second, admin = login(app), login(app, student=2), login(app, admin=True)
    identifier = reserve(first)
    reserve(second, start_time='13:00', end_time='14:00')
    with app.app_context():
        db.session.add_all([
            BlockedTime(date='2026-09-15', seat_number=2, reason='Only this date', kind='seats'),
            RecurringBlock(weekday=1, start_minute=900, end_minute=960, reason='Tuesday class'),
            Reservation(student_pk=1, student_id='202600001', student_name='Test student 1',
                        date='2026-09-15', start_minute=540, end_minute=570, seat_number=3, status='cancelled'),
            Reservation(student_pk=2, student_id='202600002', student_name='Test student 2',
                        date='2026-09-15', start_minute=540, end_minute=570, seat_number=4, status='no_show'),
        ])
        db.session.commit()
    page = admin.get('/admin?date=2026-09-15&q=Test+student+1').get_data(as_text=True)
    assert page.count('data-seat-number=') == 27
    # Seat overview always includes other students, even if the list is filtered.
    panel = page.split('id="adminSeat1"', 1)[1].split('id="adminSeat2"', 1)[0]
    assert '10:00–12:00' in panel and '13:00–14:00' in panel
    assert 'Test student 2' in panel and '예약 관리로 이동' in panel
    assert 'Only this date' in page and 'Tuesday class' in page
    assert '취소' in page and '미방문(No-show)' in page
    assert f'id="booking-{identifier}"' in page
    next_day = admin.get('/admin?date=2026-09-16').get_data(as_text=True).split('<noscript>', 1)[0]
    assert 'Only this date' not in next_day and 'Tuesday class' not in next_day
    assert first.get('/admin?date=2026-09-15').status_code == 403
    assert app.test_client().get('/admin?date=2026-09-15').status_code == 302


def test_admin_seat_colors_keep_visits_in_details_and_reservation_list_first(app):
    student, other, admin = login(app), login(app, student=2), login(app, admin=True)
    visited = reserve(student, date='2026-09-14')
    reserve(other, date='2026-09-14', start_time='13:00', end_time='14:00', seat_number=2)
    with app.app_context():
        db.session.get(Reservation, visited).is_attended = True
        db.session.add(BlockedTime(date='2026-09-14', seat_number=3, reason='Maintenance', kind='seats'))
        db.session.commit()
    app.config['NOW_PROVIDER'] = lambda: datetime(2026, 9, 14, 10, 10, tzinfo=ZoneInfo('Asia/Seoul'))
    page = admin.get('/admin').get_data(as_text=True)
    for number, label in ((1, '예약 있음'), (2, '예약 있음'), (3, '차단 일정'), (4, '예약 없음')):
        assert f'aria-label="PC {number}, {label}, 상세 보기"' in page
    assert 'map-attended' not in page
    assert page.index(f'id="booking-{visited}"') < page.index('class="card admin-seat-overview"')
    assert page.count('class="admin-seat-panel"') == 27
    assert page.count('aria-pressed="false"') == 27
    panel = page.split('id="adminSeat1"', 1)[1].split('id="adminSeat2"', 1)[0]
    assert 'aria-labelledby="adminSeatTitle1" hidden' in panel and '이용 중' in panel
