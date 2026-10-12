document.addEventListener('DOMContentLoaded', () => {
    const editor = document.querySelector('.calendar-event-editor');
    if (editor) {
        const allDay = editor.elements.all_day, fields = editor.querySelector('[data-calendar-time-fields]');
        const sync = () => {
            fields.hidden = allDay.checked;
            fields.querySelectorAll('select').forEach(field => { field.disabled = allDay.checked; field.required = !allDay.checked; });
        };
        allDay.addEventListener('change', sync); sync();
    }
    const calendar = document.querySelector('[data-lab-calendar]');
    if (!calendar) return;
    const strip = document.querySelector('[data-lab-status]');
    let data = JSON.parse(calendar.querySelector('[data-calendar-data]').textContent);
    let selected = calendar.querySelector('[data-date][aria-pressed="true"]')?.dataset.date || data.today, requestId = 0;
    const make = (tag, className, text) => {
        const element = document.createElement(tag); element.className = className; element.textContent = text; return element;
    };
    const selectDay = (day, focus = false) => {
        selected = day.date;
        calendar.querySelectorAll('[data-date]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.date === selected)));
        const title = calendar.querySelector('#calendar-day-title'); title.textContent = `${day.date} (${day.weekday})`;
        calendar.querySelector('[data-calendar-hours]').textContent = day.hours;
        calendar.querySelector('[data-calendar-reason]').textContent = day.display_reason;
        const list = calendar.querySelector('[data-calendar-events]'); list.replaceChildren(); list.hidden = !day.display_events.length;
        day.display_events.forEach(item => {
            const li = document.createElement('li');
            li.dataset.kind = item.kind;
            const title = item.display_title || item.title;
            const heading = make('strong', '', title);
            li.append(make('span', 'calendar-event-time', item.time), heading);
            list.append(li);
        });
        if (focus) title.focus({preventScroll: true});
    };
    const draw = () => {
        const focusedDate = document.activeElement?.dataset.date;
        const grid = calendar.querySelector('[data-calendar-grid]'); grid.replaceChildren();
        const today = data.today;
        data.week_views.forEach(week => {
            const row = make('div', 'calendar-week', ''); row.style.setProperty('--lanes', week.lanes);
            week.days.forEach((day, index) => {
            if (!day) {
                const blank = make('span', 'calendar-day-blank', ''); blank.setAttribute('aria-hidden', 'true');
                blank.style.gridColumn = index + 1; blank.style.gridRow = 1; row.append(blank); return;
            }
            const button = make('button', `calendar-day ${day.closed ? 'is-closed' : 'is-open'} ${day.date === today ? 'is-today' : ''}`, '');
            button.type = 'button'; button.dataset.date = day.date;
            button.style.gridColumn = index + 1; button.style.gridRow = 1;
            button.setAttribute('aria-label', `${day.date} ${day.weekday}요일, ${day.hours}${day.summary_label ? `, ${day.summary_label}` : ''}${day.events.length ? `, 일정 ${day.events.length}건` : ''}`);
            const number = make('span', 'calendar-day-number', '');
            number.append(make('span', 'calendar-day-digit', String(Number(day.date.slice(-2)))));
            button.append(number);
            if (day.cell_label) {
                const mark = make('span', 'calendar-event-mark', day.cell_label);
                mark.title = day.cell_label;
                button.append(mark);
            }
            if (day.more_events) button.append(make('span', 'calendar-more', `+${day.more_events}`));
            row.append(button);
            });
            week.spans.forEach(span => {
                const bar = make('button', 'calendar-span', ''); bar.type = 'button';
                bar.dataset.kind = span.kind; bar.dataset.eventDate = span.date;
                bar.style.gridColumn = `${span.column + 1} / span ${span.length}`; bar.style.gridRow = 1;
                bar.style.setProperty('--lane', span.lane);
                bar.title = `${span.date}–${span.through} · ${span.title}`;
                bar.setAttribute('aria-label', `${span.date}부터 ${span.through}까지 ${span.time}, ${span.title}. 일정 상세 보기`);
                bar.append(make('span', '', span.title)); row.append(bar);
            });
            grid.append(row);
        });
        calendar.querySelector('[data-month-title]').textContent = `${data.year}년 ${data.month}월`;
        calendar.dataset.month = `${data.year}-${String(data.month).padStart(2, '0')}`;
        const controls = calendar.querySelectorAll('[data-calendar-month]');
        [data.previous, data.following].forEach((month, i) => {
            const link = controls[i]; link.dataset.calendarMonth = month || '';
            if (month) { link.href = `/?month=${month}#lab-calendar`; link.removeAttribute('aria-disabled'); link.removeAttribute('tabindex'); }
            else { link.removeAttribute('href'); link.setAttribute('aria-disabled','true'); link.tabIndex = -1; }
        });
        selectDay(data.days.find(day => day.date === selected) || data.days.find(day => day.date === today) || data.days[0]);
        if (focusedDate) calendar.querySelector(`[data-date="${focusedDate}"]`)?.focus({preventScroll: true});
    };
    const loadMonth = async (month, chooseToday = false) => {
        const id = ++requestId;
        try {
            let response = await fetch(`/api/lab/calendar?month=${encodeURIComponent(month)}`, {cache:'no-store'});
            if (response.status === 404 && month !== data.today.slice(0,7)) {
                response = await fetch(`/api/lab/calendar?month=${data.today.slice(0,7)}`, {cache:'no-store'});
            }
            if (!response.ok) throw new Error();
            const result = await response.json();
            if (id !== requestId) return;
            data = result;
            if (chooseToday) selected = data.today;
            draw(); calendar.querySelector('[data-calendar-error]').textContent = '';
        } catch (_) {
            if (id === requestId) calendar.querySelector('[data-calendar-error]').textContent = '일정을 갱신하지 못했습니다. 새로고침해 주세요.';
        }
    };
    const updateStatus = async () => {
        try {
            const response = await fetch('/api/lab/status', {cache:'no-store'});
            if (!response.ok) throw new Error();
            const status = await response.json();
            strip.dataset.state = status.state;
            strip.querySelector('[data-status-dot]').className = `lab-status-dot status-${status.state}`;
            for (const key of ['label','hours']) strip.querySelector(`[data-status-${key}]`).textContent = status[key];
            strip.querySelector('[data-status-booking]').hidden = status.reservation_open;
            strip.querySelector('[data-status-updated]').textContent = status.checked_label;
        } catch (_) {
            strip.dataset.state = 'closed';
            strip.querySelector('[data-status-label]').textContent = '운영 상태 확인 필요';
            strip.querySelector('[data-status-dot]').className = 'lab-status-dot status-closed';
            strip.querySelector('[data-status-updated]').textContent = '마지막 조회 결과';
        }
    };
    calendar.addEventListener('click', event => {
        const button = event.target.closest('[data-date], [data-event-date]');
        if (button) { selectDay(data.days.find(day => day.date === (button.dataset.date || button.dataset.eventDate)), true); return; }
        const link = event.target.closest('[data-calendar-month], [data-calendar-today]');
        if (!link) return;
        event.preventDefault();
        if (link.getAttribute('aria-disabled') === 'true') return;
        const today = data.today;
        loadMonth(link.dataset.calendarMonth || today.slice(0,7), link.hasAttribute('data-calendar-today'));
    });
    const refresh = async () => { if (!document.hidden) { await updateStatus(); await loadMonth(calendar.dataset.month); } };
    setInterval(refresh, 60000);
    document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
});
