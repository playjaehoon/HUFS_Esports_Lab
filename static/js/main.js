document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('reservationForm');
    if (!form) return;
    const room = document.getElementById('labRoom');
    const date = document.getElementById('res_date');
    const start = document.getElementById('start_time');
    const end = document.getElementById('end_time');
    const submit = document.getElementById('submitReservation');
    const status = document.getElementById('availabilityStatus');
    const summary = document.getElementById('bookingSummary');
    const error = document.getElementById('bookingError');
    const csrf = document.querySelector('meta[name="csrf-token"]').content;
    const groups = [
        ['left-wall-top', [17, 18, 19, 20, 21]],
        ['left-wall-bottom', [22, 23, 24, 25, 26, 27]],
        ['center-island-top', [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]],
        ['center-island-bottom', [11, 12, 13, 14, 15, 16]],
    ];
    const validSeats = new Set(JSON.parse(form.dataset.seats));
    const buttons = new Map();
    let selected = null, ready = false, pending = false, controller, version = 0;
    groups.forEach(([className, numbers]) => {
        const group = document.createElement('div');
        group.className = `${className} ${className.startsWith('center') ? 'island-grid' : 'seat-col'}`;
        numbers.filter(n => validSeats.has(n)).forEach(number => {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = `seat${number <= 10 ? ' high-perf' : ''}`;
            button.textContent = number;
            button.disabled = true;
            button.setAttribute('aria-pressed', 'false');
            button.setAttribute('aria-label', `PC ${number}, 시간 선택 필요`);
            button.addEventListener('click', () => {
                if (!ready || pending || button.disabled) return;
                selected = number;
                buttons.forEach((b, n) => {
                    b.classList.toggle('selected', n === number);
                    b.setAttribute('aria-pressed', String(n === number));
                });
                summary.textContent = `${date.value} · ${start.value}:00–${end.value}:00 · PC ${number}`;
                submit.disabled = false;
            });
            group.appendChild(button);
            buttons.set(number, button);
        });
        room.appendChild(group);
    });

    async function availability() {
        const requestVersion = ++version;
        controller?.abort();
        controller = new AbortController();
        ready = false;
        selected = null;
        submit.disabled = true;
        error.textContent = '';
        buttons.forEach(button => {
            button.disabled = true;
            button.classList.remove('selected', 'occupied');
            button.setAttribute('aria-pressed', 'false');
        });
        summary.textContent = '좌석을 선택해 주세요.';
        if (!date.value || !start.value || !end.value) {
            status.textContent = '날짜와 시간을 먼저 선택해 주세요.';
            return;
        }
        status.textContent = '좌석 상태를 확인하고 있습니다…';
        try {
            const params = new URLSearchParams({date: date.value, start_time: start.value, end_time: end.value});
            const response = await fetch(`/api/availability?${params}`, {signal: controller.signal});
            const data = await response.json();
            if (requestVersion !== version) return;
            if (!response.ok) throw new Error(data.message || '좌석 상태를 확인할 수 없습니다.');
            const occupied = new Set(data.occupied_seats);
            const blocked = new Set(data.blocked_seats);
            buttons.forEach((button, number) => {
                const unavailable = occupied.has(number) || blocked.has(number);
                button.disabled = unavailable;
                button.classList.toggle('occupied', unavailable);
                button.setAttribute('aria-label', `PC ${number}${number <= 10 ? ', 고성능' : ''}, ${blocked.has(number) ? '점검 또는 이용 제한' : occupied.has(number) ? '예약됨' : '예약 가능'}`);
            });
            ready = true;
            status.textContent = '예약할 좌석을 선택하세요. 최종 확정 시 다시 확인합니다.';
        } catch (failure) {
            if (failure.name === 'AbortError' || requestVersion !== version) return;
            status.textContent = failure.message || '연결을 확인하고 시간을 다시 선택해 주세요.';
        }
    }
    [date, start, end].forEach(field => field.addEventListener('change', availability));
    form.addEventListener('submit', async e => {
        e.preventDefault();
        if (!ready || selected === null || pending) return;
        pending = true;
        submit.disabled = true;
        [date, start, end].forEach(field => field.disabled = true);
        try {
            const response = await fetch('/api/reserve', {
                method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
                body: JSON.stringify({date: date.value, start_time: start.value, end_time: end.value, seat_number: selected}),
            });
            const data = await response.json();
            if (!response.ok || !data.success) throw new Error(data.message || '예약에 실패했습니다.');
            window.location.assign(data.redirect_url);
        } catch (failure) {
            await availability();
            error.textContent = `${failure.message || '연결 오류가 발생했습니다.'} 내 예약에서 처리 여부를 확인해 주세요.`;
        } finally {
            pending = false;
            [date, start, end].forEach(field => field.disabled = false);
        }
    });
});
