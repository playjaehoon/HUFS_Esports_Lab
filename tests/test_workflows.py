from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Barrier
from zoneinfo import ZoneInfo
import pytest
from sqlalchemy import inspect
from werkzeug.security import check_password_hash, generate_password_hash

from models import Admin, AuditEvent, BlockedTime, DailyBooking, RecurringBlock, Reservation, ReservationSlot, Student, db, utcnow
from conftest import PASSWORD, booking, csrf, login, post, reserve


def test_registration_is_immediate_and_password_is_only_hashed(app):
    client = app.test_client()
    response = post(client, '/register', {'student_number': '202699999', 'name': 'Test new',
                                         'password': PASSWORD, 'password_confirm': PASSWORD})
    assert response.status_code == 302
    assert client.get('/my/reservations').status_code == 200
    with app.app_context():
        user = db.session.scalar(db.select(Student).where(Student.student_number == '202699999'))
        assert check_password_hash(user.password_hash, PASSWORD)
        assert not {'pin_plain', 'is_approved'} & {c['name'] for c in inspect(db.engine).get_columns('student')}


def test_student_login_and_registration_open_reservation_screen(app):
    client = app.test_client()
    response = post(client, '/login', {'student_number': '202600001', 'password': PASSWORD})
    assert response.status_code == 302
    assert response.headers['Location'].endswith('/')
    assert '좌석 예약' in client.get('/').get_data(as_text=True)

    post(client, '/logout')
    response = post(client, '/register', {'student_number': '202699998', 'name': 'New student',
                                          'password': PASSWORD, 'password_confirm': PASSWORD})
    assert response.status_code == 302
    assert response.headers['Location'].endswith('/')


@pytest.mark.parametrize('changes', [{'student_number': 'bad'}, {'name': '   '}, {'password': '12345'}, {'password': '12a456'}, {'password_confirm': 'different'}])
def test_bad_registration_is_rejected(app, changes):
    client = app.test_client()
    data = {'student_number': '202699999', 'name': 'Test', 'password': PASSWORD, 'password_confirm': PASSWORD, **changes}
    assert post(client, '/register', data).status_code == 400
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(Student)) == 2


def test_csrf_and_post_only_logout(app):
    client = app.test_client()
    assert client.post('/register', data={'name': 'No token'}).status_code == 400
    assert client.post('/login', data={'csrf_token': 'wrong'}).status_code == 400
    student = login(app)
    assert student.get('/logout').status_code == 405
    assert post(student, '/logout').status_code == 302
    assert student.get('/api/availability').status_code == 401


def test_every_admin_route_rejects_student(app):
    student = login(app)
    token = csrf(student)
    with app.app_context():
        before = db.session.scalar(db.select(db.func.count()).select_from(AuditEvent))
    for rule in app.url_map.iter_rules():
        if not rule.rule.startswith('/admin') or rule.endpoint in {'admin_login', 'admin_logout'}:
            continue
        path = rule.rule
        for arg in rule.arguments:
            path = path.replace(f'<int:{arg}>', '1')
        response = student.post(path, data={'csrf_token': token}) if 'POST' in rule.methods else student.get(path)
        assert response.status_code == 403, (path, response.status_code)
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(AuditEvent)) == before


@pytest.mark.parametrize('payload', [[], {}, booking(date='2026-09-13'), booking(date='2026-09-22'),
    booking(date='2026-02-30'), booking(start_time=2, end_time=4), booking(start_time=12, end_time=10),
    booking(end_time=16), booking(seat_number=999), booking(seat_number=0), booking(start_time=True),
    booking(start_time=10.5), booking(date='invalid')])
def test_bad_bookings_rejected_without_rows(app, payload):
    student = login(app)
    assert post(student, '/api/reserve', json=payload).status_code == 400
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(Reservation)) == 0


def test_availability_and_create_share_validation(app):
    student = login(app)
    assert student.get('/api/availability', query_string=booking(start_time=2,end_time=4)).status_code == 400
    assert student.post('/api/reserve', data='invalid', headers={'X-CSRFToken': csrf(student)}).status_code == 400


def test_reservation_survives_login_and_identity_change(app):
    student = login(app)
    identifier = reserve(student)
    detail = f'/my/reservations/{identifier}'
    assert student.get(detail).status_code == 200
    assert post(student, '/account', {'student_number': '202677777', 'name': 'Changed test', 'current_password': PASSWORD}).status_code == 302
    post(student, '/logout')
    assert post(student, '/login', {'student_number': '202677777','password': PASSWORD}).status_code == 302
    assert 'Changed test' in student.get(detail).get_data(as_text=True)
    with app.app_context():
        assert db.session.get(Reservation, identifier).student_pk == 1
        assert db.session.get(Reservation, identifier).student_id == '202600001'
        assert db.session.get(Reservation, identifier).booking_ip == '127.0.0.1'
    other = login(app, student=2)
    assert other.get(detail).status_code == 404
    assert post(other, detail+'/cancel').status_code == 404
    assert post(student, detail+'/cancel').status_code == 302
    assert post(student, detail+'/cancel').status_code == 302
    reserve(student, seat_number=2)


def test_identity_edit_requires_password_and_unique_number(app):
    student = login(app)
    assert post(student, '/account', {'student_number':'202677777', 'name':'Test', 'current_password':'wrong'}).status_code == 403
    assert post(student, '/account', {'student_number':'202600002', 'name':'Test', 'current_password':PASSWORD}).status_code == 409
    with app.app_context():
        assert db.session.get(Student,1).student_number == '202600001'


def test_password_change_revokes_other_sessions(app):
    first, second = login(app), login(app)
    assert post(first, '/account/password', {'current_password':PASSWORD,'password':'654321','password_confirm':'654321'}).status_code == 302
    assert first.get('/my/reservations').status_code == 200
    assert second.get('/my/reservations').status_code == 302


def test_imported_student_can_skip_password_change_prompt(app):
    with app.app_context():
        student = db.session.get(Student, 1)
        student.must_change_password = True
        db.session.commit()
    client = login(app)
    assert client.get('/').status_code == 200
    assert '나중에 하기' in client.get('/').get_data(as_text=True)
    assert client.get('/my/reservations').status_code == 302
    assert post(client, '/account/skip-password-change').status_code == 302
    assert client.get('/my/reservations').status_code == 200
    assert '나중에 하기' not in client.get('/').get_data(as_text=True)
    post(client, '/logout')
    assert post(client, '/login', {'student_number': '202600001', 'password': PASSWORD}).status_code == 302
    assert '다음 로그인 때 다시 안내합니다' in client.get('/').get_data(as_text=True)
    with app.app_context():
        assert db.session.get(Student, 1).must_change_password is True
        assert db.session.scalar(db.select(db.func.count()).select_from(AuditEvent).where(
            AuditEvent.action == 'password_change_skipped')) == 1


def test_block_applies_to_existing_session_without_losing_history(app):
    student, admin = login(app), login(app,admin=True)
    identifier = reserve(student)
    assert post(admin,'/admin/students/block/1',{'duration':'1week'}).status_code == 302
    assert post(student,'/api/reserve',json=booking(date='2026-09-16')).status_code == 403
    assert student.get(f'/my/reservations/{identifier}').status_code == 200
    assert post(student,'/account',{'student_number':'202677777','name':'Changed','current_password':PASSWORD}).status_code == 302
    assert post(student,'/api/reserve',json=booking(date='2026-09-16')).status_code == 403


def test_old_student_number_cannot_be_reused_to_escape_restriction(app):
    student, admin = login(app), login(app,admin=True)
    assert post(admin,'/admin/students/block/1',{'duration':'1week'}).status_code == 302
    assert post(student,'/account',{'student_number':'202677777','name':'Changed','current_password':PASSWORD}).status_code == 302
    outsider = app.test_client()
    assert post(outsider,'/register',{'student_number':'202600001','name':'New account',
                                    'password':PASSWORD,'password_confirm':PASSWORD}).status_code == 409
    other = login(app,student=2)
    assert post(other,'/account',{'student_number':'202600001','name':'Other','current_password':PASSWORD}).status_code == 409
    # The original owner can correct their number back, without losing the ban.
    assert post(student,'/account',{'student_number':'202600001','name':'Original','current_password':PASSWORD}).status_code == 302
    assert post(student,'/api/reserve',json=booking()).status_code == 403
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(Student)) == 2


@pytest.mark.parametrize('same_student', [False, True])
def test_concurrent_requests_create_exactly_one_booking(app, same_student):
    clients = [login(app), login(app,student=1 if same_student else 2)]
    tokens = [csrf(c) for c in clients]
    barrier = Barrier(2)
    def attempt(index):
        barrier.wait(timeout=5)
        return clients[index].post('/api/reserve',json=booking(seat_number=(index+1 if same_student else 1)),
                                   headers={'X-CSRFToken':tokens[index]}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(attempt, [0,1]))
    assert sorted(statuses) == [201,409]
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(Reservation)) == 1
        assert db.session.scalar(db.select(db.func.count()).select_from(DailyBooking)) == 1
        assert db.session.scalar(db.select(db.func.count()).select_from(ReservationSlot)) == 4


def test_blocks_conflicts_and_settings_validation(app):
    student, admin = login(app), login(app,admin=True)
    block = {'start_date':'2026-09-15','end_date':'2026-09-15','block_type':'all','seat_numbers':'1','reason':'Test maintenance'}
    assert post(admin,'/admin/block/seats',block).status_code == 302
    assert 1 in student.get('/api/availability',query_string=booking()).get_json()['blocked_seats']
    assert post(student,'/api/reserve',json=booking()).status_code == 409
    reserve(student,seat_number=2)
    assert post(admin,'/admin/block/seats',{**block,'seat_numbers':'2'}).status_code == 409
    assert post(admin,'/admin/block/seats',{**block,'block_type':'specific','start_time':'09:00'}).status_code == 400
    assert post(admin,'/admin/settings',{'max_hours':'broken'}).status_code == 400


def test_half_hour_booking_past_time_and_three_block_modes(app):
    student, admin = login(app), login(app, admin=True)
    assert post(student, '/api/reserve', json=booking(start_time='10:15', end_time='10:45')).status_code == 400
    assert post(student, '/api/reserve', json=booking(date='2026-09-14', start_time='07:30', end_time='08:00')).status_code == 400
    identifier = reserve(student, start_time='10:30', end_time='11:30')
    with app.app_context():
        reservation = db.session.get(Reservation, identifier)
        assert (reservation.start_minute, reservation.end_minute) == (630, 690)
        assert db.session.scalars(db.select(ReservationSlot.minute).order_by(ReservationSlot.minute)).all() == [630, 660]

    event_data = {'date':'2026-09-16','block_type':'specific','start_time':'13:00','end_time':'14:30','reason':'전체 행사'}
    assert post(admin, '/admin/block/event', event_data).status_code == 302
    multi = {'start_date':'2026-09-17','end_date':'2026-09-19','block_type':'all','seat_numbers':['2','3','4'],'reason':'쾌적화 운영'}
    assert post(admin, '/admin/block/seats', multi).status_code == 302
    recurring = {'weekday':'4','start_time':'09:30','end_time':'11:00','reason':'정기 수업'}
    assert post(admin, '/admin/block/recurring', recurring).status_code == 302
    assert set(student.get('/api/availability', query_string=booking(date='2026-09-17')).get_json()['blocked_seats']) >= {2,3,4}
    assert set(student.get('/api/availability', query_string=booking(date='2026-09-19')).get_json()['blocked_seats']) >= {2,3,4}
    assert len(student.get('/api/availability', query_string=booking(date='2026-09-18', start_time='09:30', end_time='10:00')).get_json()['blocked_seats']) == 27
    with app.app_context():
        group = db.session.scalar(db.select(BlockedTime).where(BlockedTime.kind == 'seats'))
        group_id = group.id
        assert db.session.scalar(db.select(db.func.count()).select_from(BlockedTime).where(BlockedTime.kind == 'seats')) == 9
        assert db.session.scalar(db.select(db.func.count()).select_from(RecurringBlock)) == 1
    assert post(admin, f'/admin/unblock/{group_id}').status_code == 302
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(BlockedTime).where(BlockedTime.kind == 'seats')) == 0


def test_admin_settings_update_student_notices_and_duration_limit(app):
    admin = login(app, admin=True)
    response = post(admin, '/admin/settings', {
        'reservation_open': '1', 'open_hour': '9', 'close_hour': '17',
        'max_hours': '2', 'advance_days': '7',
        'notice': 'Test top notice',
        'usage_notice': 'Test rule one\nTest rule two',
    })
    assert response.status_code == 302
    student = login(app)
    body = student.get('/').get_data(as_text=True)
    assert 'Test top notice' in body
    assert 'Test rule one\nTest rule two' in body
    assert 'data-max-hours="2"' in body
    assert 'id="timeError"' in body
    assert 'id="start_time" class="form-control"' in body
    assert '<option value="09:00">09:00</option>' in body
    assert '<option value="09:30">09:30</option>' in body
    assert '날짜 &amp; 시간 선택' in body
    assert '접속 IP 주소를 수집' in body
    assert 'Evnia Performance Zone' in body
    assert 'Evnia Gaming Zone' in body
    assert 'id="seatDetailDialog"' in body
    assert 'evnia-27m2n3500uk.avif' in body
    assert 'evnia-24m2n3200l.avif' in body
    assert 'dxracer-martian-pro.png' in body


def test_visit_state_guards_and_audit(app):
    student, admin = login(app), login(app,admin=True)
    identifier = reserve(student, date='2026-09-14')
    url = f'/admin/attend/{identifier}'
    assert post(admin,url,{'card_checked':'1'}).status_code == 409  # too early
    app.config['NOW_PROVIDER'] = lambda: datetime(2026,9,14,10,10,tzinfo=ZoneInfo('Asia/Seoul'))
    assert post(admin,url).status_code == 400
    assert post(admin,url,{'card_checked':'1'}).status_code == 302
    assert post(admin,url,{'card_checked':'1'}).status_code == 302
    assert post(student,f'/my/reservations/{identifier}/cancel').status_code == 409
    assert post(admin,f'/admin/unattend/{identifier}').status_code == 400
    assert post(admin,f'/admin/checkout/{identifier}').status_code == 302
    assert post(admin,url,{'card_checked':'1'}).status_code == 409
    with app.app_context():
        r = db.session.get(Reservation,identifier)
        assert r.status == 'completed' and r.checked_in_by == r.checked_out_by == 1
        assert db.session.scalar(db.select(db.func.count()).select_from(AuditEvent).where(AuditEvent.action=='check_in')) == 1


def test_student_cancel_window_after_start(app):
    student = login(app)
    identifier = reserve(student, date='2026-09-14', start_time='10:00', end_time='11:00')
    with app.app_context():
        db.session.get(Reservation, identifier).created_at = datetime(2026, 9, 14, 1, 0)
        db.session.commit()
    other = login(app, student=2)
    old = reserve(other, date='2026-09-14', start_time='10:00', end_time='11:00', seat_number=2)
    app.config['NOW_PROVIDER'] = lambda: datetime(2026, 9, 14, 10, 3, tzinfo=ZoneInfo('Asia/Seoul'))
    assert post(student, f'/my/reservations/{identifier}/cancel').status_code == 302
    with app.app_context():
        db.session.get(Reservation, old).created_at = datetime(2026, 9, 14, 0, 0)
        db.session.commit()
    app.config['NOW_PROVIDER'] = lambda: datetime(2026, 9, 14, 10, 10, tzinfo=ZoneInfo('Asia/Seoul'))
    assert post(other, f'/my/reservations/{old}/cancel').status_code == 409
    assert '예약 시작 전 또는 예약 후 5분 이내에만 직접 취소할 수 있습니다' in other.get(f'/my/reservations/{old}').get_data(as_text=True)


def test_cancelled_future_booking_cannot_be_revived(app):
    student, admin = login(app), login(app,admin=True)
    identifier = reserve(student)
    post(student,f'/my/reservations/{identifier}/cancel')
    assert post(admin,f'/admin/attend/{identifier}',{'card_checked':'1'}).status_code == 409
    with app.app_context():
        assert db.session.get(Reservation,identifier).status == 'cancelled'


def test_missed_checkin_does_not_auto_ban(app):
    student, admin = login(app), login(app,admin=True)
    identifier = reserve(student,date='2026-09-14')
    app.config['NOW_PROVIDER'] = lambda: datetime(2026,9,15,8,tzinfo=ZoneInfo('Asia/Seoul'))
    reserve(student,date='2026-09-16')
    assert post(admin,f'/admin/no-show/{identifier}',{'reason':'Test confirmed absence'}).status_code == 302
    with app.app_context():
        assert db.session.get(Reservation,identifier).status == 'no_show'
        assert db.session.get(Student,1).blocked_until is None


def test_legacy_default_admin_is_rejected_and_session_ids_fail_closed(app):
    with app.app_context():
        db.session.get(Admin,1).password_hash = generate_password_hash('admin123')
        db.session.commit()
    client = app.test_client()
    assert post(client,'/admin/login',{'username':'staff','password':'admin123'}).status_code == 403
    with client.session_transaction() as sess:
        sess['_user_id'] = 'admin_1'
    assert client.get('/admin').status_code == 302


def test_rate_limit_is_database_backed(app):
    app.config['AUTH_RATE_LIMIT_ENABLED'] = True
    first, second = app.test_client(), app.test_client()
    for index in range(10):
        response = post(first if index % 2 else second,'/login',{'student_number':'202600001','password':'wrong'})
        assert response.status_code == 200
    response = post(second,'/login',{'student_number':'202600001','password':PASSWORD})
    assert response.status_code == 429 and response.headers['Retry-After'] == '900'


def test_pages_render_for_each_role(app):
    student, admin = login(app), login(app,admin=True)
    for path in ['/', '/my/reservations','/account']:
        assert student.get(path).status_code == 200
    for path in ['/admin','/admin/students','/admin/audit']:
        assert admin.get(path).status_code == 200
    response = student.get('/account')
    assert response.headers['Cache-Control'] == 'no-store'
    assert response.headers['X-Frame-Options'] == 'DENY'


def test_layout_uses_original_logo_asset_and_short_student_pin_copy(app):
    response = app.test_client().get('/login')
    body = response.get_data(as_text=True)
    assert '/static/images/logo.png' in body
    assert 'Philips Evnia의 후원으로 마련된 한국외국어대학교 실습실' not in body
    assert '숫자 6자리' in body
