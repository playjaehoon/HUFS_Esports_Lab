from datetime import date, datetime
from zoneinfo import ZoneInfo
import pytest
from conftest import booking, login, post, reserve
from lab_schedule import month_schedule, operating_status, schedule_for_day
from models import BlockedTime, CalendarEvent, RecurringBlock, Reservation, Setting, db


def set_now(app, day='2026-09-15', time='10:00'):
    app.config['NOW_PROVIDER'] = lambda: datetime.fromisoformat(f'{day}T{time}:00').replace(tzinfo=ZoneInfo('Asia/Seoul'))


def event_form(**values):
    return {'action':'save', 'title':'공개 행사', 'kind':'rental', 'start_date':'2026-09-15',
            'end_date':'2026-09-15', 'start_time':'14:00', 'end_time':'16:00', **values}


@pytest.mark.parametrize('day', ['2026-09-19','2026-09-20','2026-10-09','2026-10-05','2026-09-25'])
def test_weekends_public_and_substitute_holidays_block_new_bookings(app, day):
    set_now(app, day, '08:00')
    student = login(app)
    availability = student.get('/api/availability', query_string=booking(date=day)).get_json()
    assert availability['blocked_seats'] == list(range(1,28))
    assert post(student, '/api/reserve', json=booking(date=day)).status_code == 409
    status = student.get('/api/lab/status').get_json()
    assert status['label'] == '휴관' and status['hours'] == '미개방'


def test_open_intervals_overlap_and_live_status_boundaries(app):
    admin = login(app, admin=True)
    assert post(admin, '/admin/calendar', event_form()).status_code == 302
    assert post(admin, '/admin/calendar', event_form(title='추가 대관', start_time='15:00', end_time='16:30')).status_code == 302
    with app.app_context():
        assert schedule_for_day(date(2026,9,15))['intervals'] == [(540,840),(990,1020)]
        for time, label in [('08:59','휴관'),('09:00','개방'),('13:59','개방'),
                            ('14:00','휴관'),('16:29','휴관'),('16:30','개방'),('17:00','휴관')]:
            set_now(app, time=time)
            assert operating_status()['label'] == label


def test_calendar_excludes_seat_blocks_private_reasons_and_student_data(app):
    with app.app_context():
        db.session.add_all([
            BlockedTime(date='2026-09-15', seat_number=2, reason='PRIVATE REPAIR', kind='seats'),
            BlockedTime(date='2026-09-15', start_minute=780, end_minute=810, reason='PRIVATE RENTAL'),
            RecurringBlock(weekday=1,start_minute=840,end_minute=900,reason='PRIVATE CLASS'),
        ])
        db.session.commit()
    public = app.test_client()
    result = public.get('/api/lab/calendar?month=2026-09')
    body = result.get_data(as_text=True)
    assert all(value not in body for value in ['PRIVATE','Test student','student_number','booking_ip','seat_number'])
    day = result.get_json()['days'][14]
    assert len(day['events']) == 2 and day['hours'] == '09:00–13:00 / 13:30–14:00 / 15:00–17:00'
    assert day['events'][1]['title'] == '정기 수업'
    assert day['events'][1]['display_title'] == '수업'
    assert 'Cache-Control' in result.headers


def test_calendar_management_roles_csrf_validation_conflicts_and_toggle(app):
    student, admin = login(app), login(app, admin=True)
    assert student.get('/admin/calendar').status_code == 403
    assert app.test_client().get('/admin/calendar').status_code == 302
    assert admin.post('/admin/calendar', data=event_form()).status_code == 400
    invalid = post(admin, '/admin/calendar', event_form(title=''))
    assert invalid.status_code == 400 and '공개 일정 제목' in invalid.get_data(as_text=True)
    assert 'calendar-admin-error' in invalid.get_data(as_text=True)
    identifier = reserve(student)
    conflict = post(admin, '/admin/calendar', event_form(start_time='10:00',end_time='11:00'))
    assert conflict.status_code == 409
    with app.app_context():
        assert db.session.get(Reservation, identifier).status == 'active'
        assert db.session.scalar(db.select(db.func.count()).select_from(CalendarEvent)) == 0
    assert post(admin, '/admin/calendar', event_form()).status_code == 302
    with app.app_context():
        item_id = db.session.scalar(db.select(CalendarEvent.id))
    assert post(admin, '/admin/calendar', {'action':'toggle','id':item_id}).status_code == 302
    day = admin.get('/api/lab/calendar?month=2026-09').get_json()['days'][14]
    assert day['hours'] == '09:00–17:00' and not day['events']
    assert post(admin, '/admin/calendar', {'action':'toggle','id':item_id}).status_code == 302
    data = booking(start_time='14:00',end_time='15:00')
    assert len(student.get('/api/availability',query_string=data).get_json()['blocked_seats']) == 27
    assert post(student, '/api/reserve', json=data).status_code == 409


def test_calendar_and_closed_days_are_reflected_in_admin_seat_overview(app):
    admin = login(app, admin=True)
    assert post(admin, '/admin/calendar', event_form(title='학부 단체 대관')).status_code == 302
    page = admin.get('/admin?date=2026-09-15').get_data(as_text=True)
    assert page.count(', 차단 일정, 상세 보기') == 27
    assert '학부 단체 대관' in page and '14:00–16:00' in page
    holiday = admin.get('/admin?date=2026-10-09').get_data(as_text=True)
    assert holiday.count(', 차단 일정, 상세 보기') == 27 and '한글날' in holiday
    next_day = admin.get('/admin?date=2026-09-16').get_data(as_text=True)
    assert next_day.count(', 예약 없음, 상세 보기') == 27 and '학부 단체 대관' not in next_day.split('<noscript>', 1)[0]


def test_period_weekday_edit_and_information_event_do_not_block(app):
    admin, student = login(app, admin=True), login(app)
    assert post(admin, '/admin/calendar', event_form(kind='event', title='<script>text</script>',
         start_date='2026-09-14',end_date='2026-09-22',weekday='1')).status_code == 302
    data = admin.get('/api/lab/calendar?month=2026-09').get_json()['days']
    assert not data[13]['events'] and not data[15]['events']
    assert data[14]['events'][0]['blocks'] is False and data[21]['events']
    assert reserve(student, start_time='14:00',end_time='15:00')
    page = admin.get('/admin/calendar').get_data(as_text=True)
    assert '<script>text</script>' not in page and '&lt;script&gt;' in page
    with app.app_context():
        item_id = db.session.scalar(db.select(CalendarEvent.id))
    assert post(admin, '/admin/calendar', event_form(id=item_id,kind='event',title='수정')).status_code == 302
    assert admin.get(f'/admin/calendar?edit={item_id}').status_code == 200


def test_operating_weekdays_and_booking_stop_are_separate(app):
    student, admin = login(app), login(app, admin=True)
    identifier = reserve(student)
    assert post(admin,'/admin/calendar',{'action':'weekdays','weekdays':['0','2','3','4']}).status_code == 302
    set_now(app)
    assert admin.get('/api/lab/status').get_json()['label'] == '휴관'
    with app.app_context():
        assert db.session.get(Reservation, identifier).status == 'active'
    assert post(admin,'/admin/calendar',{'action':'weekdays','weekdays':['0','1','2','3','4']}).status_code == 302
    with app.app_context():
        db.session.scalar(db.select(Setting).where(Setting.key=='reservation_open')).value = '0'
        db.session.commit()
    status = admin.get('/api/lab/status').get_json()
    assert status['label'] == '개방' and status['reservation_open'] is False


def test_calendar_month_navigation_leap_year_and_invalid_month(app):
    public = app.test_client()
    for month in ['2026-00','2026-13','2026-9','1999-01','xxxx']:
        assert public.get('/api/lab/calendar?month='+month).status_code == 400
    with app.app_context():
        result = month_schedule(2028,2)
        assert len(result['days']) == 29 and len(result['weeks']) == 5
        result = month_schedule(2026,12)
        assert result['following'] == '2027-01' and result['previous'] == '2026-11'
    home = public.get('/').get_data(as_text=True)
    assert 'data-lab-status' in home and 'data-lab-calendar' in home


def test_calendar_publication_period_is_enforced_without_changing_booking_window(app):
    admin, student = login(app, admin=True), login(app)
    public = app.test_client()
    assert post(student, '/admin/calendar', {'action':'publication','calendar_future_months':'0'}).status_code == 403
    assert admin.post('/admin/calendar', data={'action':'publication','calendar_future_months':'0'}).status_code == 400
    assert post(admin, '/admin/calendar', {'action':'publication','calendar_future_months':'13'}).status_code == 400
    assert post(admin, '/admin/calendar', {'action':'publication','calendar_future_months':'0'}).status_code == 302
    assert public.get('/api/lab/calendar?month=2026-10').status_code == 404
    assert public.get('/?month=2026-10').status_code == 404
    current = public.get('/api/lab/calendar?month=2026-09').get_json()
    assert current['following'] is None and current['publication']['through'] == '2026-09'
    assert public.get('/api/lab/calendar?month=2026-08').status_code == 200
    # Staff can prepare unpublished dates; shortening disclosure preserves records.
    assert post(admin, '/admin/calendar', event_form(title='미공개 학부 행사', kind='event',
           start_date='2027-01-12', end_date='2027-01-12', all_day='1')).status_code == 302
    assert '미공개 학부 행사' in admin.get('/admin/calendar').get_data(as_text=True)
    assert post(admin, '/admin/calendar', {'action':'publication','calendar_future_months':'4'}).status_code == 302
    future = public.get('/api/lab/calendar?month=2027-01').get_json()
    assert future['days'][11]['events'][0]['title'] == '미공개 학부 행사' and future['following'] is None
    assert reserve(student)  # Calendar publication is not a booking restriction.
    set_now(app, '2026-12-15')
    assert public.get('/api/lab/calendar?month=2027-04').status_code == 200
    assert public.get('/api/lab/calendar?month=2027-05').status_code == 404


def test_compact_status_shows_only_current_state_and_keeps_event_in_calendar(app):
    admin = login(app, admin=True)
    assert post(admin, '/admin/calendar', event_form(title='특강', kind='class')).status_code == 302
    set_now(app, time='14:30')
    status = app.test_client().get('/api/lab/status').get_json()
    assert status['label'] == '휴관'
    assert status['checked_label'] == '9월 15일 14:30 기준'
    set_now(app, time='13:00')
    assert app.test_client().get('/api/lab/status').get_json()['label'] == '개방'
    day = app.test_client().get('/api/lab/calendar?month=2026-09').get_json()['days'][14]
    assert day['events'][0]['title'] == '특강'
    home = app.test_client().get('/').get_data(as_text=True)
    strip = home.split('data-lab-status',1)[1].split('</section>',1)[0]
    assert '한국 시간' not in strip and 'data-status-detail' not in strip and '운영시간' in strip
    assert '특강' not in strip and '오늘 휴관' not in strip and '정기 휴무' not in strip
    assert '등록된 수업·대관·행사가 없습니다.' not in home
    assert '좌석별 예약 가능 여부는 예약 화면에서 확인해 주세요.' not in home
