"""Public calendar and authenticated staff schedule editing."""
import json
import re
from flask import flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user
from auth_helpers import admin_required
from booking import RuleError, event, korea_now, parse_date, rules, time_minutes, write_transaction
from lab_schedule import KINDS, WEEKDAYS, applies, calendar_publication, month_schedule, operating_status, open_weekdays
from models import CalendarEvent, Reservation, Setting, db


def read_month(value):
    if not re.fullmatch(r'20\d{2}-(?:0[1-9]|1[0-2])', value):
        raise RuleError('2000~2099년의 월을 선택해 주세요.')
    return map(int, value.split('-'))


def published_calendar(month=None):
    value = month or korea_now().strftime('%Y-%m')
    year, number = read_month(value)
    publication = calendar_publication()
    if not publication['from'] <= value <= publication['through']:
        raise RuleError('아직 공개되지 않은 달의 일정입니다.', 404)
    calendar = month_schedule(year, number)
    if calendar['previous'] < publication['from']:
        calendar['previous'] = None
    if calendar['following'] > publication['through']:
        calendar['following'] = None
    calendar['publication'] = publication
    calendar['today'] = korea_now().date().isoformat()
    return calendar


def calendar_context(month=None):
    calendar = published_calendar(month)
    today = korea_now().date().isoformat()
    selected = next((day for day in calendar['days'] if day['date'] == today), calendar['days'][0])
    return {'calendar': calendar, 'selected_day': selected, 'today': today}


def check_event_conflicts(item):
    if not item.blocks_reservations or not item.is_active:
        return
    query = db.select(Reservation).where(Reservation.status == 'active',
        Reservation.date >= max(item.start_date, korea_now().date().isoformat()), Reservation.date <= item.end_date)
    if item.start_minute is not None:
        query = query.where(Reservation.start_minute < item.end_minute, Reservation.end_minute > item.start_minute)
    if any(applies(item, parse_date(reservation.date)) for reservation in db.session.scalars(query)):
        raise RuleError('기존 예약과 겹칩니다. 예약을 먼저 확인한 뒤 일정을 등록해 주세요.', 409)


def register_calendar_routes(app):
    @app.get('/api/lab/status')
    def lab_status():
        response = jsonify(operating_status())
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.get('/api/lab/calendar')
    def lab_calendar():
        response = jsonify(published_calendar(request.args.get('month')))
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.route('/admin/calendar', methods=['GET', 'POST'])
    @admin_required
    def admin_calendar():
        error, status = '', 200
        values = request.form.to_dict() if request.method == 'POST' else {}
        editing = db.get_or_404(CalendarEvent, request.args['edit']) if request.args.get('edit') else None
        if request.method == 'POST':
            try:
                with write_transaction():
                    action = request.form.get('action')
                    if action == 'weekdays':
                        weekdays = sorted(set(request.form.getlist('weekdays')))
                        if any(day not in {'0','1','2','3','4','5','6'} for day in weekdays):
                            raise RuleError('운영 요일을 확인해 주세요.')
                        setting = db.session.scalar(db.select(Setting).where(Setting.key == 'open_weekdays'))
                        value = json.dumps([int(day) for day in weekdays])
                        if setting:
                            setting.value = value
                        else:
                            db.session.add(Setting(key='open_weekdays', value=value))
                        event(f'admin:{current_user.id}', 'calendar_weekdays', 'settings', value)
                    elif action == 'publication':
                        months = values.get('calendar_future_months', '')
                        if not re.fullmatch(r'(?:[0-9]|1[0-2])', months):
                            raise RuleError('달력 공개 기간을 0~12개월로 선택해 주세요.')
                        setting = db.session.scalar(db.select(Setting).where(Setting.key == 'calendar_future_months'))
                        if setting:
                            setting.value = months
                        else:
                            db.session.add(Setting(key='calendar_future_months', value=months))
                        event(f'admin:{current_user.id}', 'calendar_publication', 'settings', months)
                    elif action == 'toggle':
                        item = db.get_or_404(CalendarEvent, request.form.get('id', type=int))
                        item.is_active = not item.is_active
                        check_event_conflicts(item)
                        event(f'admin:{current_user.id}', 'calendar_toggle', item.id, str(item.is_active))
                    elif action == 'save':
                        first, last = parse_date(values.get('start_date')), parse_date(values.get('end_date'))
                        if not 2000 <= first.year <= last.year <= 2099 or not 0 <= (last-first).days < 366:
                            raise RuleError('기간은 시작일 포함 최대 366일로 입력해 주세요.')
                        title, kind = values.get('title', '').strip(), values.get('kind')
                        if not 1 <= len(title) <= 100 or any(ord(c) < 32 for c in title):
                            raise RuleError('공개 일정 제목을 1~100자로 입력해 주세요.')
                        if kind not in KINDS:
                            raise RuleError('일정 종류를 선택해 주세요.')
                        weekday = values.get('weekday', '')
                        if weekday and weekday not in {'0','1','2','3','4','5','6'}:
                            raise RuleError('반복 요일을 확인해 주세요.')
                        if values.get('all_day') == '1':
                            start = end = None
                        else:
                            start, end = time_minutes(values.get('start_time'), '시작 시간'), time_minutes(values.get('end_time'), '종료 시간')
                            if start >= end:
                                raise RuleError('종료 시간은 시작 시간 이후로 선택해 주세요.')
                        identifier = request.form.get('id', type=int)
                        item = db.get_or_404(CalendarEvent, identifier) if identifier else CalendarEvent(is_active=True)
                        item.title, item.kind = title, kind
                        item.start_date, item.end_date = first.isoformat(), last.isoformat()
                        item.weekday = int(weekday) if weekday else None
                        item.start_minute, item.end_minute = start, end
                        item.blocks_reservations = kind != 'event' or values.get('blocks_reservations') == '1'
                        check_event_conflicts(item)
                        db.session.add(item)
                        db.session.flush()
                        event(f'admin:{current_user.id}', 'calendar_save', item.id, title)
                    else:
                        raise RuleError('저장할 내용을 확인해 주세요.')
                flash('달력 공개 기간을 저장했습니다. 예약 가능 기간은 유지됩니다.' if action == 'publication'
                      else '일정을 저장했습니다. 달력과 신규 예약에 반영됩니다. 기존 예약은 유지됩니다.')
                return redirect(url_for('admin_calendar'))
            except RuleError as exc:
                error, status = str(exc), exc.status
        if editing and request.method == 'GET':
            from booking import clock
            values = {'id': editing.id, 'title': editing.title, 'kind': editing.kind,
                      'start_date': editing.start_date, 'end_date': editing.end_date,
                      'weekday': str(editing.weekday) if editing.weekday is not None else '',
                      'all_day': '1' if editing.start_minute is None else '',
                      'start_time': clock(editing.start_minute) if editing.start_minute is not None else '',
                      'end_time': clock(editing.end_minute) if editing.end_minute is not None else '',
                      'blocks_reservations': '1' if editing.blocks_reservations else ''}
        return render_template('admin_calendar.html', values=values, error=error, kinds=KINDS,
            weekdays=WEEKDAYS, open_days=open_weekdays(), policy=rules(), publication=calendar_publication(),
            events=db.session.scalars(db.select(CalendarEvent).order_by(CalendarEvent.start_date.desc(), CalendarEvent.id.desc())).all()), status
