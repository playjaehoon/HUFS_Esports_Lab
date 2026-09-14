document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('reservationForm');
    if (!form) return;
    const room = document.getElementById('labRoom'), date = document.getElementById('res_date');
    const start = document.getElementById('start_time'), duration = document.getElementById('duration');
    const end = document.getElementById('end_time'), submit = document.getElementById('submitReservation');
    const status = document.getElementById('availabilityStatus'), summary = document.getElementById('bookingSummary');
    const error = document.getElementById('bookingError'), timeError = document.getElementById('timeError');
    const endPreview = document.getElementById('endTimePreview');
    const closeMinute = Number(form.dataset.closeMinute), loadedAt = Date.now();
    const csrf = document.querySelector('meta[name="csrf-token"]').content;
    const groups = [['left-wall-top',[17,18,19,20,21]],['left-wall-bottom',[22,23,24,25,26,27]],
        ['center-island-top',[1,2,3,4,5,6,7,8,9,10]],['center-island-bottom',[11,12,13,14,15,16]]];
    const validSeats = new Set(JSON.parse(form.dataset.seats)), buttons = new Map();
    let selected = null, ready = false, pending = false, controller, version = 0;
    const parseTime = value => { const m = /^(\d{2}):(\d{2})$/.exec(value || ''); return m ? +m[1] * 60 + +m[2] : NaN; };
    const formatTime = value => `${String(Math.floor(value / 60)).padStart(2,'0')}:${String(value % 60).padStart(2,'0')}`;
    const formatDuration = value => value < 60 ? `${value}분` : `${Math.floor(value/60)}시간${value%60 ? ` ${value%60}분` : ''}`;
    const currentServerMinute = () => +form.dataset.serverMinute + Math.floor((Date.now() - loadedAt) / 60000);

    groups.forEach(([className, numbers]) => {
        const group = document.createElement('div');
        group.className = `${className} ${className.startsWith('center') ? 'island-grid' : 'seat-col'}`;
        numbers.filter(n => validSeats.has(n)).forEach(number => {
            const button = document.createElement('button');
            button.type = 'button'; button.className = `seat${number <= 10 ? ' high-perf' : ''}`;
            button.textContent = number; button.disabled = true; button.setAttribute('aria-pressed','false');
            button.addEventListener('click', () => {
                if (!ready || pending || button.disabled) return;
                selected = number;
                buttons.forEach((b,n) => { b.classList.toggle('selected',n===number); b.setAttribute('aria-pressed',String(n===number)); });
                summary.textContent = `${date.value} · ${start.value}–${end.value} · PC ${number}`; submit.disabled = false;
            });
            group.appendChild(button); buttons.set(number,button);
        }); room.appendChild(group);
    });

    function timeProblem() {
        endPreview.textContent = '이용 시간을 선택하면 종료 시간을 보여드립니다.';
        if (!start.value || !duration.value) return '';
        const startMinute = parseTime(start.value), useMinutes = +duration.value;
        if (!Number.isFinite(startMinute) || startMinute % 30) return '시작 시간은 30분 단위로 선택해 주세요.';
        if (date.value === form.dataset.serverDate && startMinute <= currentServerMinute()) return '이미 지난 시간은 예약할 수 없습니다.';
        if (startMinute + useMinutes > closeMinute) return `운영 종료 시간(${formatTime(closeMinute)})을 넘습니다. 시작 시간이나 이용 시간을 줄여 주세요.`;
        end.value = formatTime(startMinute + useMinutes);
        endPreview.textContent = `${start.value} 시작 · ${end.value} 종료`;
        return '';
    }

    async function availability() {
        const requestVersion = ++version; controller?.abort(); controller = new AbortController();
        ready = false; selected = null; submit.disabled = true; error.textContent = ''; timeError.textContent = '';
        start.removeAttribute('aria-invalid'); duration.removeAttribute('aria-invalid');
        buttons.forEach(button => { button.disabled=true; button.classList.remove('selected','occupied'); button.setAttribute('aria-pressed','false'); });
        summary.textContent = '날짜와 시간을 먼저 선택해 주세요.';
        if (!date.value || !start.value || !duration.value) { status.textContent='날짜, 시작 시간과 이용 시간을 선택해 주세요.'; return; }
        const problem = timeProblem();
        if (problem) { timeError.textContent=problem; start.setAttribute('aria-invalid','true'); duration.setAttribute('aria-invalid','true'); status.textContent='이용 시간을 다시 선택해 주세요.'; summary.textContent='시간 설정을 확인해 주세요.'; return; }
        summary.textContent = `${formatDuration(+duration.value)} 이용 · 좌석을 선택해 주세요.`; status.textContent='좌석 상태를 확인하고 있습니다…';
        try {
            const params = new URLSearchParams({date:date.value,start_time:start.value,end_time:end.value});
            const response = await fetch(`/api/availability?${params}`,{signal:controller.signal}), data = await response.json();
            if (requestVersion !== version) return;
            if (!response.ok) throw new Error(data.message || '좌석 상태를 확인할 수 없습니다.');
            const occupied = new Set(data.occupied_seats), blocked = new Set(data.blocked_seats);
            buttons.forEach((button,number) => { const unavailable=occupied.has(number)||blocked.has(number); button.disabled=unavailable; button.classList.toggle('occupied',unavailable); button.setAttribute('aria-label',`PC ${number}${number<=10?', 고성능':''}, ${blocked.has(number)?'점검 또는 이용 제한':occupied.has(number)?'예약됨':'예약 가능'}`); });
            ready=true; status.textContent='예약할 좌석을 선택하세요. 최종 확정 시 다시 확인합니다.';
        } catch (failure) { if (failure.name !== 'AbortError' && requestVersion === version) status.textContent=failure.message || '연결을 확인하고 시간을 다시 선택해 주세요.'; }
    }
    [date,start,duration].forEach(field => field.addEventListener('change',availability));
    form.addEventListener('submit', async event => {
        event.preventDefault(); if (!ready || selected===null || pending) return;
        pending=true; submit.disabled=true; [date,start,duration].forEach(field => field.disabled=true);
        try {
            const response = await fetch('/api/reserve',{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':csrf},body:JSON.stringify({date:date.value,start_time:start.value,end_time:end.value,seat_number:selected})});
            const data = await response.json(); if (!response.ok || !data.success) throw new Error(data.message || '예약에 실패했습니다.'); window.location.assign(data.redirect_url);
        } catch (failure) { await availability(); error.textContent=`${failure.message || '연결 오류가 발생했습니다.'} 내 예약에서 처리 여부를 확인해 주세요.`; }
        finally { pending=false; [date,start,duration].forEach(field => field.disabled=false); }
    });
});
