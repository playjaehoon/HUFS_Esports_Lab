document.addEventListener('DOMContentLoaded', () => {
    const labRoom = document.getElementById('labRoom');
    if (!labRoom) return;

    // Build the seat layout
    const layout = [
        { id: 'lw-top', class: 'left-wall-top', type: 'col', start: 17, end: 21 },
        { id: 'lw-bot', class: 'left-wall-bottom', type: 'col', start: 22, end: 27 },
        { id: 'ci-top', class: 'center-island-top', type: 'block', rows: 5, start: 1 },
        { id: 'ci-bot', class: 'center-island-bottom', type: 'block', rows: 3, start: 11 }
    ];

    let allSeats = [];

    layout.forEach(group => {
        const groupEl = document.createElement('div');
        groupEl.className = group.class;
        groupEl.style.position = 'absolute';

        if (group.type === 'col') {
            groupEl.className += ' seat-col';
            let html = '';
            for (let i = group.start; i <= group.end; i++) {
                let hp = i <= 10 ? ' high-perf' : '';
                html += `<div class="seat${hp}" data-seat="${i}">${i}</div>`;
                allSeats.push(i);
            }
            groupEl.innerHTML = html;
        } else if (group.type === 'block') {
            groupEl.style.display = 'flex';
            groupEl.style.gap = '20px';

            const col1 = document.createElement('div');
            col1.className = 'seat-col';
            const col2 = document.createElement('div');
            col2.className = 'seat-col';

            let current = group.start;
            for (let i = 0; i < group.rows; i++) {
                let hp1 = current <= 10 ? ' high-perf' : '';
                col1.innerHTML += `<div class="seat${hp1}" data-seat="${current}">${current}</div>`;
                allSeats.push(current);
                current++;
                let hp2 = current <= 10 ? ' high-perf' : '';
                col2.innerHTML += `<div class="seat${hp2}" data-seat="${current}">${current}</div>`;
                allSeats.push(current);
                current++;
            }

            groupEl.appendChild(col1);
            groupEl.appendChild(col2);
        }

        labRoom.appendChild(groupEl);
    });

    // Handle seat selection logic
    const seatSelectionInput = document.getElementById('seat_number');
    const selectedSeatDisplay = document.getElementById('selected_seat_display');
    const seats = document.querySelectorAll('.seat');

    // Inputs that affect availability
    const dateInput = document.getElementById('res_date');
    const startTimeInput = document.getElementById('start_time');
    const endTimeInput = document.getElementById('end_time');

    // Set today's date and 1-week limit based on LOCAL time, not UTC.
    // getTimezoneOffset() returns minutes, usually -540 for KST (UTC+9)
    const now = new Date();
    const localOffset = now.getTimezoneOffset() * 60000;
    const localToday = new Date(now.getTime() - localOffset);

    const todayStr = localToday.toISOString().split('T')[0];
    dateInput.min = todayStr;

    const nextWeek = new Date(localToday.getTime());
    nextWeek.setDate(nextWeek.getDate() + 7);
    const nextWeekStr = nextWeek.toISOString().split('T')[0];
    dateInput.max = nextWeekStr;

    function checkAvailability() {
        const date = dateInput.value;
        const start = startTimeInput.value;
        const end = endTimeInput.value;

        if (!date || !start || !end) return;

        // Reset all seats to available
        seats.forEach(s => {
            s.classList.remove('occupied');
            s.style.cursor = 'pointer';
        });

        fetch(`/api/availability?date=${date}&start_time=${start}&end_time=${end}`)
            .then(res => res.json())
            .then(data => {
                if (data.blocked) {
                    showToast(data.message);
                    seats.forEach(s => {
                        s.classList.add('occupied');
                        s.classList.remove('selected');
                        s.style.cursor = 'not-allowed';
                    });
                    seatSelectionInput.value = '';
                    selectedSeatDisplay.value = '';
                    return;
                }

                if (data.occupied_seats) {
                    data.occupied_seats.forEach(num => {
                        const occupiedSeat = document.querySelector(`.seat[data-seat="${num}"]`);
                        if (occupiedSeat) {
                            occupiedSeat.classList.add('occupied');
                            occupiedSeat.classList.remove('selected');
                            // If the currently selected seat becomes occupied, clear the selection
                            if (seatSelectionInput.value == num) {
                                seatSelectionInput.value = '';
                                selectedSeatDisplay.value = '';
                            }
                        }
                    });
                }
            })
            .catch(err => console.error("Error fetching availability", err));
    }

    dateInput.addEventListener('change', checkAvailability);
    startTimeInput.addEventListener('change', checkAvailability);
    endTimeInput.addEventListener('change', checkAvailability);

    seats.forEach(seat => {
        seat.addEventListener('click', () => {
            if (seat.classList.contains('occupied')) {
                showToast("이 좌석은 선택한 시간에 이미 예약되어 있습니다.");
                return;
            }

            seats.forEach(s => s.classList.remove('selected'));
            seat.classList.add('selected');

            const seatNum = seat.getAttribute('data-seat');
            seatSelectionInput.value = seatNum;
            selectedSeatDisplay.value = `PC ${seatNum}번 좌석`;
        });
    });

    // Handle Time duration constraints visually
    startTimeInput.addEventListener('change', () => {
        const start = parseInt(startTimeInput.value);
        if (!start) return;

        // Auto-select end_time slightly logic or constrain
        Array.from(endTimeInput.options).forEach(opt => {
            const val = parseInt(opt.value);
            if (val) {
                if (val <= start) opt.disabled = true;
                else opt.disabled = false;
            }
        });
    });

    // Form submission via AJAX
    const form = document.getElementById('reservationForm');
    form.addEventListener('submit', (e) => {
        e.preventDefault();

        if (!seatSelectionInput.value) {
            alert('좌석을 선택해주세요!');
            return;
        }

        const payload = {
            student_id: document.getElementById('student_id').value,
            student_name: document.getElementById('student_name').value,
            date: dateInput.value,
            start_time: startTimeInput.value,
            end_time: endTimeInput.value,
            seat_number: seatSelectionInput.value
        };

        fetch('/api/reserve', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    alert(data.message);
                    window.location.reload();
                } else {
                    alert(data.message);
                }
            });
    });

    function showToast(msg) {
        const container = document.getElementById('jsToastContainer');
        const toast = document.createElement('div');
        toast.className = 'toast';
        toast.innerHTML = `<span>${msg}</span><button onclick="this.parentElement.remove()" style="background:none; border:none; cursor:pointer; margin-left:1rem; font-size:1.2rem;">&times;</button>`;
        container.appendChild(toast);
        setTimeout(() => toast.remove(), 4000);
    }
});
