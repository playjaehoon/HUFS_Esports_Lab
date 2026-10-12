"""Period presentation clips weeks/months without changing per-day restrictions."""
from conftest import login, post
from test_lab_calendar import event_form, set_now


def test_period_title_once_per_week_with_full_detail_on_every_day(app):
    admin = login(app, admin=True)
    assert post(admin, '/admin/calendar', event_form(kind='general', title='시범 운영 기간',
        start_date='2026-09-14', end_date='2026-09-28', all_day='1')).status_code == 302
    public = app.test_client()
    month = public.get('/api/lab/calendar?month=2026-09').get_json()
    spans = [span for week in month['week_views'] for span in week['spans']]
    assert [span['length'] for span in spans] == [6, 7, 2]
    assert sum(span['length'] for span in spans) == 15
    for day in month['days'][13:28]:
        assert day['display_events'][0]['display_title'] == '시범 운영 기간'
        assert day['cell_label'] != '시범 운영 기간'
    html = public.get('/?month=2026-09').get_data(as_text=True)
    assert html.count('<span>시범 운영 기간</span></button>') == 3


def test_period_clips_at_month_boundary_and_does_not_join_same_titles(app):
    admin = login(app, admin=True)
    for first, last in [('2026-10-29','2026-11-03'), ('2026-10-26','2026-10-27')]:
        assert post(admin, '/admin/calendar', event_form(kind='general', title='같은 제목',
            start_date=first, end_date=last, all_day='1')).status_code == 302
    public = app.test_client()
    october = public.get('/api/lab/calendar?month=2026-10').get_json()
    last_week = october['week_views'][-1]['spans']
    assert len(last_week) == 2
    assert {item['date'] for item in last_week} == {'2026-10-26','2026-10-29'}
    assert len({item['key'] for item in last_week}) == 2
    november = public.get('/api/lab/calendar?month=2026-11').get_json()
    span = november['week_views'][0]['spans'][0]
    assert (span['column'], span['length'], span['date'], span['through']) == (0,3,'2026-11-01','2026-11-03')


def test_overlapping_periods_have_two_lanes_and_more_count_keeps_full_details(app):
    admin = login(app, admin=True)
    for title in ['안내 A', '안내 B', '안내 C']:
        assert post(admin, '/admin/calendar', event_form(kind='general', title=title,
            start_date='2026-09-14', end_date='2026-09-18', all_day='1')).status_code == 302
    month = app.test_client().get('/api/lab/calendar?month=2026-09').get_json()
    week = month['week_views'][2]
    assert week['lanes'] == 2 and len(week['spans']) == 2
    assert {item['lane'] for item in week['spans']} == {0,1}
    for day in month['days'][13:18]:
        assert day['more_events'] == 1 and len(day['display_events']) == 3


def test_closure_bar_and_public_information_keep_reservation_rules(app):
    admin = login(app, admin=True)
    for values in [dict(kind='closed', title='방학 휴관'), dict(kind='general', title='온라인 안내')]:
        assert post(admin, '/admin/calendar', event_form(start_date='2026-09-14',
            end_date='2026-09-20', all_day='1', **values)).status_code == 302
    month = app.test_client().get('/api/lab/calendar?month=2026-09').get_json()
    assert month['week_views'][2]['lanes'] == 2
    for day in month['days'][13:20]:
        assert day['closed'] and not day['intervals']
        assert day['display_reason'] == '' and day['cell_label'] == ''
        assert [item['display_title'] for item in day['display_events']] == ['방학 휴관','온라인 안내']


def test_paused_state_names_class_rental_and_temporary_closure(app):
    admin = login(app, admin=True)
    for kind, label in [('class','수업 중'), ('rental','대관 중'), ('closed','일시 휴관')]:
        assert post(admin, '/admin/calendar', event_form(kind=kind, title=label)).status_code == 302
        set_now(app, time='14:30')
        assert app.test_client().get('/api/lab/status').get_json()['label'] == label
        month = app.test_client().get('/api/lab/calendar?month=2026-09').get_json()
        identifier = int(month['days'][14]['events'][0]['span_key'].split(':')[1])
        assert post(admin, '/admin/calendar', {'action':'delete','id':identifier}).status_code == 302
    for kind in ['class','rental']:
        assert post(admin, '/admin/calendar', event_form(kind=kind, title=kind)).status_code == 302
    assert app.test_client().get('/api/lab/status').get_json()['label'] == '수업·대관 중'
