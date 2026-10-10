"""Shared public schedule, opening intervals and Korea-time live status."""
import calendar
from datetime import date, timedelta
from functools import lru_cache
import json
import holidays
from booking import clock, korea_now, rules
from models import BlockedTime, CalendarEvent, RecurringBlock, db

KINDS = {'class': '수업', 'rental': '단체 대관', 'event': '행사', 'closed': '휴관'}
WEEKDAYS = ('월', '화', '수', '목', '금', '토', '일')


@lru_cache(maxsize=16)
def public_holidays(year):
    return holidays.country_holidays('KR', years=year, language='ko', observed=True)


def open_weekdays(policy=None):
    values = json.loads((policy or rules())['open_weekdays'])
    return set(values)


def applies(item, day):
    return (item.start_date <= day.isoformat() <= item.end_date and
            (item.weekday is None or item.weekday == day.weekday()))


def schedule_sources(first, last):
    return (
        db.session.scalars(db.select(CalendarEvent).where(CalendarEvent.is_active.is_(True),
            CalendarEvent.start_date <= last.isoformat(), CalendarEvent.end_date >= first.isoformat()).order_by(CalendarEvent.id)).all(),
        db.session.scalars(db.select(BlockedTime).where(BlockedTime.seat_number.is_(None),
            BlockedTime.date >= first.isoformat(), BlockedTime.date <= last.isoformat()).order_by(BlockedTime.id)).all(),
        db.session.scalars(db.select(RecurringBlock).order_by(RecurringBlock.id)).all())


def schedule_for_day(day, sources=None, policy=None):
    policy = policy or rules()
    events, blocks, recurring = sources or schedule_sources(day, day)
    opening, closing = policy['open_hour'] * 60, policy['close_hour'] * 60
    items = []
    def add(title, kind, start, end, blocked):
        display_title = KINDS[kind] if title in {'정기 수업', '대관·행사'} else title
        items.append({'title': title, 'display_title': display_title, 'kind': kind, 'label': KINDS[kind], 'start': start,
                      'end': end, 'blocks': blocked, 'time': '종일' if start is None else f'{clock(start)}–{clock(end)}'})
    for item in events:
        if applies(item, day):
            add(item.title, item.kind, item.start_minute, item.end_minute, item.blocks_reservations)
    # Internal block reasons and all individual-seat blocks remain private.
    for item in blocks:
        if item.date == day.isoformat():
            add('대관·행사', 'rental', item.start_minute, item.end_minute, True)
    for item in recurring:
        if item.weekday == day.weekday():
            add('정기 수업', 'class', item.start_minute, item.end_minute, True)
    items.sort(key=lambda item: (item['start'] or 0, item['title']))
    holiday = public_holidays(day.year).get(day, '')
    closed_reason = holiday or ('정기 휴무' if day.weekday() not in open_weekdays(policy) else '')
    intervals = [] if closed_reason else [(opening, closing)]
    for item in items:
        if not item['blocks']:
            continue
        start = opening if item['start'] is None else item['start']
        end = closing if item['end'] is None else item['end']
        intervals = [(a, b) for lo, hi in intervals
                     for a, b in ((lo, min(hi, start)), (max(lo, end), hi)) if a < b]
    return {'date': day.isoformat(), 'weekday': WEEKDAYS[day.weekday()], 'holiday': holiday,
            'closed_reason': closed_reason or ('수업·대관·휴관 일정' if not intervals else ''),
            'intervals': intervals, 'hours': ' / '.join(f'{clock(a)}–{clock(b)}' for a, b in intervals) or '미개방',
            'events': items, 'closed': not intervals}


def operating_status(now=None):
    now = now or korea_now()
    policy = rules()
    schedule = schedule_for_day(now.date(), policy=policy)
    minute = now.hour * 60 + now.minute + now.second / 60
    active = next(((a, b) for a, b in schedule['intervals'] if a <= minute < b), None)
    upcoming = next(((a, b) for a, b in schedule['intervals'] if a > minute), None)
    if schedule['closed']:
        state, detail = 'closed', schedule['closed_reason']
    elif active:
        state, detail = 'open', f'{clock(active[1])}까지 개방'
    elif minute < policy['open_hour'] * 60:
        state, detail = 'closed', f'{clock(schedule["intervals"][0][0])} 개방'
    elif upcoming:
        state, detail = 'paused', f'{clock(upcoming[0])} 다시 개방'
    else:
        state, detail = 'closed', '다음 이용일의 일정을 확인해 주세요.'
    # The main strip shows only the current state; reasons stay in the calendar.
    label = '개방' if active else '휴관'
    return {'state': state, 'label': label, 'detail': detail, 'date': schedule['date'],
            'hours': schedule['hours'], 'reservation_open': policy['reservation_open'] == '1',
            'checked_at': now.isoformat(), 'checked_time': now.strftime('%H:%M'),
            'checked_label': f'{now.month}월 {now.day}일 {now:%H:%M} 기준'}


def calendar_publication():
    """Calendar disclosure is separate from the student booking window."""
    now = korea_now()
    months = int(rules()['calendar_future_months'])
    index = now.year * 12 + now.month - 1 + months
    year, month = divmod(index, 12)
    return {'months': months, 'through': f'{year:04d}-{month + 1:02d}', 'from': '2000-01'}


def month_schedule(year, month):
    first = date(year, month, 1)
    last = date(year, month, calendar.monthrange(year, month)[1])
    sources, policy = schedule_sources(first, last), rules()
    days = [schedule_for_day(first + timedelta(days=n), sources, policy) for n in range(last.day)]
    # Sunday-first calendar, matching common Korean calendars.
    leading = (first.weekday() + 1) % 7
    cells = [None] * leading + days
    cells += [None] * (-len(cells) % 7)
    previous = first - timedelta(days=1)
    following = last + timedelta(days=1)
    return {'year': year, 'month': month, 'weeks': [cells[i:i+7] for i in range(0, len(cells), 7)],
            'days': days, 'previous': previous.strftime('%Y-%m'), 'following': following.strftime('%Y-%m')}
