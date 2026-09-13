"""HTTP handlers. Business rules and DB writes live in explicit boundaries."""
from datetime import timedelta
import re

from flask import abort, flash, jsonify, redirect, render_template, request, session, url_for
from flask_login import current_user, login_user, logout_user, login_required
from werkzeug.security import check_password_hash, generate_password_hash
from sqlalchemy.orm import joinedload

from auth_helpers import admin_required, student_required, throttle
from booking import (SEATS, RuleError, allowed_student, blocked_seats, booking_input,
                     ends_at, event, integer, korea_now, parse_date, release, rules,
                     starts_at, write_transaction)
from models import (Admin, AuditEvent, BlockedTime, DailyBooking, Reservation,
                    ReservationSlot, Setting, Student, StudentNumberClaim, db, utcnow)


def identity(form):
    number, name = form.get('student_number', '').strip(), form.get('name', '').strip()
    if not re.fullmatch(r'[0-9]{9}', number):
        raise RuleError('학번은 9자리 숫자로 입력해 주세요.')
    if not 1 <= len(name) <= 50 or any(ord(c) < 32 for c in name):
        raise RuleError('이름은 1~50자로 입력해 주세요.')
    return number, name


def valid_password(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]{6}', value):
        raise RuleError('비밀번호는 숫자 6자리로 입력해 주세요.')
    return value


def actor():
    role = 'admin' if isinstance(current_user._get_current_object(), Admin) else 'student'
    return f'{role}:{current_user.id}'


def own_reservation(identifier):
    return db.first_or_404(db.select(Reservation).where(Reservation.id == identifier,
                                                       Reservation.student_pk == current_user.id))


def claim_number(number, owner):
    claim = db.session.get(StudentNumberClaim, number)
    if claim is not None and claim.student_pk != owner:
        raise RuleError('이미 사용된 학번입니다. 정보 정정은 운영진에게 문의해 주세요.', 409)
    if claim is None:
        db.session.add(StudentNumberClaim(student_number=number, student_pk=owner))


def register_routes(app):
    @app.route('/')
    @login_required
    def index():
        if isinstance(current_user._get_current_object(), Admin):
            return redirect(url_for('admin_dashboard'))
        policy = rules()
        now = korea_now()
        return render_template('index.html', student=current_user, policy=policy,
                               notice=policy['notice'], seats=SEATS,
                               today=now.date().isoformat(),
                               last_date=(now.date() + timedelta(days=policy['advance_days'])).isoformat())

    @app.route('/login', methods=['GET', 'POST'])
    def student_login():
        if current_user.is_authenticated:
            return redirect(url_for('index'))
        if request.method == 'POST':
            number = request.form.get('student_number', '').strip()
            throttle('student-login', number)
            password = request.form.get('password', '')
            user = db.session.scalar(db.select(Student).where(Student.student_number == number))
            if user and user.is_active and len(password) <= 128 and check_password_hash(user.password_hash, password):
                session.clear()
                login_user(user)
                session.permanent = True
                return redirect(url_for('account' if user.must_change_password else 'my_reservations'))
            flash('학번 또는 비밀번호를 확인해 주세요.')
        return render_template('student_login.html')

    @app.route('/register', methods=['GET', 'POST'])
    def student_register():
        if current_user.is_authenticated:
            return redirect(url_for('index'))
        if request.method == 'POST':
            number, name = identity(request.form)
            throttle('register', number, limit=5)
            password = valid_password(request.form.get('password'))
            if password != request.form.get('password_confirm'):
                raise RuleError('비밀번호 확인이 일치하지 않습니다.')
            with write_transaction():
                user = Student(student_number=number, name=name, password_hash=generate_password_hash(password))
                db.session.add(user)
                db.session.flush()
                claim_number(number, user.id)
                event(f'student:{user.id}', 'register', user.id)
            session.clear()
            login_user(user)
            session.permanent = True
            flash('가입이 완료되었습니다. 예약 후 이용 당일 학생증을 보여주세요.')
            return redirect(url_for('my_reservations'))
        return render_template('student_register.html')

    @app.route('/logout', methods=['POST'])
    @app.route('/admin/logout', methods=['POST'], endpoint='admin_logout')
    @login_required
    def logout():
        logout_user()
        session.clear()
        return redirect(url_for('student_login'))

    @app.route('/admin/login', methods=['GET', 'POST'])
    def admin_login():
        if current_user.is_authenticated:
            return redirect(url_for('index'))
        if request.method == 'POST':
            username = request.form.get('username', '').strip()
            throttle('admin-login', username)
            password = request.form.get('password', '')
            user = db.session.scalar(db.select(Admin).where(Admin.username == username))
            if user and len(password) <= 128 and check_password_hash(user.password_hash, password):
                # Refuse the public legacy bootstrap credential, even on old databases.
                if check_password_hash(user.password_hash, 'admin123'):
                    raise RuleError('관리자 초기 비밀번호를 서버에서 변경해야 합니다.', 403)
                session.clear()
                login_user(user)
                session.permanent = True
                return redirect(url_for('admin_dashboard'))
            flash('아이디 또는 비밀번호를 확인해 주세요.')
        return render_template('admin_login.html')

    @app.route('/account', methods=['GET', 'POST'])
    @student_required
    def account():
        if request.method == 'POST':
            number, name = identity(request.form)
            throttle('profile-password', str(current_user.id))
            with write_transaction():
                if not check_password_hash(current_user.password_hash, request.form.get('current_password', '')):
                    raise RuleError('현재 비밀번호를 확인해 주세요.', 403)
                claim_number(current_user.student_number, current_user.id)
                claim_number(number, current_user.id)
                current_user.student_number, current_user.name = number, name
                event(actor(), 'profile_update', current_user.id)
            flash('회원정보를 수정했습니다. 기존 예약과 이용 이력은 유지됩니다.')
            return redirect(url_for('account'))
        return render_template('account.html')

    @app.route('/account/password', methods=['POST'])
    @student_required
    def change_password():
        throttle('change-password', str(current_user.id))
        password = valid_password(request.form.get('password'))
        if password != request.form.get('password_confirm'):
            raise RuleError('비밀번호 확인이 일치하지 않습니다.')
        user = current_user._get_current_object()
        with write_transaction():
            if not check_password_hash(user.password_hash, request.form.get('current_password', '')):
                raise RuleError('현재 비밀번호를 확인해 주세요.', 403)
            user.password_hash = generate_password_hash(password)
            user.must_change_password = False
            user.session_version += 1
            event(actor(), 'password_change', user.id)
        session.clear()
        login_user(user)
        session.permanent = True
        flash('비밀번호를 변경했습니다. 다른 기기의 로그인은 해제됩니다.')
        return redirect(url_for('account'))

    @app.route('/account/skip-password-change', methods=['POST'])
    @student_required
    def skip_password_change():
        if not current_user.must_change_password:
            return redirect(url_for('index'))
        with write_transaction():
            current_user.must_change_password = False
            event(actor(), 'password_change_skipped', current_user.id)
        flash('비밀번호 변경을 건너뛰었습니다. 필요할 때 내 정보에서 변경할 수 있습니다.')
        return redirect(url_for('my_reservations'))

    @app.route('/my/reservations')
    @student_required
    def my_reservations():
        page = max(1, request.args.get('page', default=1, type=int))
        query = db.select(Reservation).where(Reservation.student_pk == current_user.id).order_by(
            Reservation.date.desc(), Reservation.start_time.desc(), Reservation.id.desc())
        history = db.paginate(query, page=page, per_page=20, error_out=False)
        now = korea_now()
        next_booking = db.session.scalar(db.select(Reservation).where(
            Reservation.student_pk == current_user.id, Reservation.status == 'active',
            db.or_(Reservation.date > now.date().isoformat(),
                   db.and_(Reservation.date == now.date().isoformat(), Reservation.end_time > now.hour))
        ).order_by(Reservation.date, Reservation.start_time).limit(1))
        return render_template('my_reservations.html', history=history, next_booking=next_booking, now=now, starts_at=starts_at)

    @app.route('/my/reservations/<int:reservation_id>')
    @student_required
    def reservation_detail(reservation_id):
        return render_template('reservation_detail.html', r=own_reservation(reservation_id),
                               now=korea_now(), starts_at=starts_at)

    @app.route('/my/reservations/<int:reservation_id>/cancel', methods=['POST'])
    @student_required
    def cancel_own_reservation(reservation_id):
        with write_transaction():
            reservation = own_reservation(reservation_id)
            if reservation.status == 'cancelled':
                return redirect(url_for('reservation_detail', reservation_id=reservation.id))
            if reservation.status != 'active' or reservation.is_attended or starts_at(reservation) <= korea_now():
                raise RuleError('시작 전 예약만 직접 취소할 수 있습니다. 운영진에게 문의해 주세요.', 409)
            reservation.status, reservation.cancelled_at = 'cancelled', utcnow()
            release(reservation)
            event(actor(), 'cancel', reservation.id)
        flash('예약을 취소했습니다.')
        return redirect(url_for('reservation_detail', reservation_id=reservation_id))

    @app.route('/api/availability')
    @student_required
    def get_availability():
        date, start, end, _ = booking_input(request.args.to_dict(), seat_required=False)
        blocked = blocked_seats(date, start, end)
        occupied = set(db.session.scalars(db.select(ReservationSlot.seat_number).where(
            ReservationSlot.date == date, ReservationSlot.hour >= start, ReservationSlot.hour < end)))
        return jsonify(occupied_seats=sorted(occupied), blocked_seats=sorted(blocked))

    @app.route('/api/reserve', methods=['POST'])
    @student_required
    def make_reservation():
        data = request.get_json(silent=True)
        with write_transaction():
            allowed_student(current_user)
            date, start, end, seat = booking_input(data)
            if seat in blocked_seats(date, start, end):
                raise RuleError('해당 시간 또는 좌석은 이용이 제한되어 있습니다.', 409)
            # Unique constraints are the final arbiter for both quota and occupancy.
            reservation = Reservation(student_pk=current_user.id, student_id=current_user.student_number,
                                      student_name=current_user.name, date=date, start_time=start,
                                      end_time=end, seat_number=seat)
            db.session.add(reservation)
            db.session.flush()
            db.session.add(DailyBooking(student_pk=current_user.id, date=date, reservation_id=reservation.id))
            db.session.add_all([ReservationSlot(reservation_id=reservation.id, date=date,
                                                seat_number=seat, hour=hour) for hour in range(start, end)])
            event(actor(), 'reserve', reservation.id)
            identifier = reservation.id
        return jsonify(success=True, message='예약이 완료되었습니다.',
                       redirect_url=url_for('reservation_detail', reservation_id=identifier)), 201

    @app.route('/admin')
    @admin_required
    def admin_dashboard():
        day = request.args.get('date', korea_now().date().isoformat())
        parse_date(day)
        query = db.select(Reservation).options(joinedload(Reservation.student)).where(Reservation.date == day)
        term = request.args.get('q', '').strip()[:50]
        if term:
            query = query.join(Student).where(db.or_(Student.student_number.contains(term, autoescape=True),
                                                     Student.name.contains(term, autoescape=True)))
        reservations = db.session.scalars(query.order_by(Reservation.start_time, Reservation.seat_number)).all()
        blocks = db.session.scalars(db.select(BlockedTime).where(BlockedTime.date >= korea_now().date().isoformat()).order_by(BlockedTime.date)).all()
        return render_template('admin_dashboard.html', reservations=reservations, day=day, term=term,
                               policy=rules(), blocks=blocks, seats=SEATS, now=korea_now(), ends_at=ends_at)

    @app.route('/admin/students')
    @admin_required
    def admin_students():
        term = request.args.get('q', '').strip()[:50]
        query = db.select(Student).order_by(Student.student_number)
        if term:
            query = query.where(db.or_(Student.student_number.contains(term, autoescape=True), Student.name.contains(term, autoescape=True)))
        students = db.paginate(query, page=max(1, request.args.get('page', 1, type=int)), per_page=30, error_out=False)
        return render_template('admin_students.html', students=students, term=term, now=utcnow())

    @app.route('/admin/students/approve/<int:student_id>', methods=['POST'])
    @admin_required
    def admin_approve_student(student_id):
        raise RuleError('가입 승인은 더 이상 필요하지 않습니다.', 410)

    @app.route('/admin/students/delete/<int:student_id>', methods=['POST'])
    @admin_required
    def admin_delete_student(student_id):
        # Deactivate instead of deleting identity/history and allowing re-registration.
        with write_transaction():
            user = db.get_or_404(Student, student_id)
            user.archived, user.session_version = True, user.session_version + 1
            for reservation in db.session.scalars(db.select(Reservation).where(Reservation.student_pk == user.id,
                    Reservation.status == 'active', Reservation.date >= korea_now().date().isoformat())):
                if not reservation.is_attended:
                    reservation.status, reservation.cancelled_at = 'cancelled', utcnow()
                    release(reservation)
            event(actor(), 'deactivate_student', user.id)
        flash('계정을 비활성화했습니다. 이용 이력은 보존됩니다.')
        return redirect(url_for('admin_students'))

    @app.route('/admin/students/block/<int:student_id>', methods=['POST'])
    @admin_required
    def admin_block_student(student_id):
        duration = request.form.get('duration')
        if duration not in {'1week', '2weeks', 'permanent', 'unblock'}:
            raise RuleError('제한 기간을 확인해 주세요.')
        with write_transaction():
            user = db.get_or_404(Student, student_id)
            user.blocked_until = None if duration == 'unblock' else utcnow() + timedelta(days={'1week': 7, '2weeks': 14, 'permanent': 36500}[duration])
            event(actor(), 'student_restriction', user.id, duration)
        flash('이용 제한을 변경했습니다. 기존 예약 취소는 별도로 확인해 주세요.')
        return redirect(url_for('admin_students'))

    @app.route('/admin/block', methods=['POST'])
    @admin_required
    def admin_block_time():
        date = parse_date(request.form.get('date')).isoformat()
        mode = request.form.get('block_type')
        start = end = None
        if mode == 'specific':
            start, end = integer(request.form.get('start_time'), '시작 시간'), integer(request.form.get('end_time'), '종료 시간')
            if not 0 <= start < end <= 24:
                raise RuleError('차단 시간 범위를 확인해 주세요.')
        elif mode != 'all':
            raise RuleError('차단 방식을 확인해 주세요.')
        seat = integer(request.form.get('seat_number'), '좌석') if request.form.get('seat_number') else None
        if seat is not None and seat not in SEATS:
            raise RuleError('좌석 번호를 확인해 주세요.')
        reason = request.form.get('reason', '').strip()
        if not 1 <= len(reason) <= 200:
            raise RuleError('차단 사유를 1~200자로 입력해 주세요.')
        with write_transaction():
            conflicting = db.select(Reservation).where(Reservation.date == date, Reservation.status == 'active')
            if seat is not None:
                conflicting = conflicting.where(Reservation.seat_number == seat)
            if start is not None:
                conflicting = conflicting.where(Reservation.start_time < end, Reservation.end_time > start)
            if db.session.scalar(conflicting.limit(1)):
                raise RuleError('기존 예약과 겹칩니다. 해당 예약을 안내·취소한 뒤 차단해 주세요.', 409)
            block = BlockedTime(date=date, start_time=start, end_time=end, seat_number=seat, reason=reason)
            db.session.add(block)
            db.session.flush()
            event(actor(), 'block_time', block.id, reason)
        return redirect(url_for('admin_dashboard', date=date))

    @app.route('/admin/unblock/<int:block_id>', methods=['POST'])
    @admin_required
    def admin_unblock_time(block_id):
        with write_transaction():
            db.session.delete(db.get_or_404(BlockedTime, block_id))
            event(actor(), 'unblock_time', block_id)
        return redirect(url_for('admin_dashboard'))

    @app.route('/admin/cancel/<int:reservation_id>', methods=['POST'])
    @admin_required
    def admin_cancel_reservation(reservation_id):
        with write_transaction():
            reservation = db.get_or_404(Reservation, reservation_id)
            if reservation.status not in {'active', 'cancelled'} or reservation.is_attended:
                raise RuleError('이용 중·종료된 예약은 취소할 수 없습니다.', 409)
            if reservation.status != 'cancelled':
                reservation.status, reservation.cancelled_at = 'cancelled', utcnow()
                release(reservation)
                event(actor(), 'cancel', reservation.id)
        return redirect(url_for('admin_dashboard'))

    @app.route('/admin/attend/<int:reservation_id>', methods=['POST'])
    @admin_required
    def admin_attend_reservation(reservation_id):
        if request.form.get('card_checked') != '1':
            raise RuleError('학생증과 당일 예약 정보를 먼저 대조해 주세요.')
        with write_transaction():
            reservation = db.get_or_404(Reservation, reservation_id)
            if reservation.status != 'active' or reservation.date != korea_now().date().isoformat() or korea_now() >= ends_at(reservation):
                raise RuleError('당일 종료 전 활성 예약만 체크인할 수 있습니다.', 409)
            if korea_now() < starts_at(reservation):
                raise RuleError('예약 시작 시간부터 체크인할 수 있습니다.', 409)
            allowed_student(reservation.student)
            if reservation.seat_number in blocked_seats(reservation.date, reservation.start_time, reservation.end_time):
                raise RuleError('이용이 제한된 시간 또는 좌석입니다.', 409)
            if not reservation.is_attended:
                reservation.is_attended, reservation.checked_in_at, reservation.checked_in_by = True, utcnow(), current_user.id
                reservation.student_id, reservation.student_name = reservation.student.student_number, reservation.student.name
                event(actor(), 'check_in', reservation.id)
        return redirect(url_for('admin_dashboard'))

    @app.route('/admin/checkout/<int:reservation_id>', methods=['POST'])
    @admin_required
    def admin_checkout(reservation_id):
        with write_transaction():
            reservation = db.get_or_404(Reservation, reservation_id)
            if reservation.status == 'completed':
                return redirect(url_for('admin_dashboard'))
            if reservation.status != 'active' or not reservation.is_attended:
                raise RuleError('체크인한 예약만 이용 종료할 수 있습니다.', 409)
            reservation.status, reservation.checked_out_at, reservation.checked_out_by = 'completed', utcnow(), current_user.id
            event(actor(), 'check_out', reservation.id)
        return redirect(url_for('admin_dashboard'))

    @app.route('/admin/unattend/<int:reservation_id>', methods=['POST'])
    @admin_required
    def admin_unattend_reservation(reservation_id):
        reason = request.form.get('reason', '').strip()
        if not 1 <= len(reason) <= 200:
            raise RuleError('체크인 정정 사유를 입력해 주세요.')
        with write_transaction():
            reservation = db.get_or_404(Reservation, reservation_id)
            if reservation.status != 'active' or not reservation.is_attended:
                raise RuleError('이용 중인 예약만 체크인을 정정할 수 있습니다.', 409)
            reservation.is_attended = False
            event(actor(), 'undo_check_in', reservation.id, reason)
            reservation.checked_in_at = reservation.checked_in_by = None
        return redirect(url_for('admin_dashboard'))

    @app.route('/admin/no-show/<int:reservation_id>', methods=['POST'])
    @admin_required
    def admin_no_show(reservation_id):
        reason = request.form.get('reason', '').strip()
        if not 1 <= len(reason) <= 200:
            raise RuleError('노쇼 확인 사유를 입력해 주세요.')
        with write_transaction():
            reservation = db.get_or_404(Reservation, reservation_id)
            if reservation.status != 'active' or reservation.is_attended or ends_at(reservation) > korea_now():
                raise RuleError('종료 시간이 지난 미방문 예약만 노쇼로 확정할 수 있습니다.', 409)
            reservation.status = 'no_show'
            event(actor(), 'no_show', reservation.id, reason)
        flash('노쇼를 기록했습니다. 이용 제한은 학생 관리에서 별도로 적용하세요.')
        return redirect(url_for('admin_dashboard'))

    @app.route('/admin/settings', methods=['POST'])
    @admin_required
    def admin_settings():
        values = {key: integer(request.form.get(key), key) for key in ('open_hour', 'close_hour', 'max_hours', 'advance_days')}
        if not 0 <= values['open_hour'] < values['close_hour'] <= 24 or not 1 <= values['max_hours'] <= values['close_hour'] - values['open_hour'] or not 0 <= values['advance_days'] <= 60:
            raise RuleError('운영 시간·최대 시간·예약 기간의 범위를 확인해 주세요.')
        values['reservation_open'] = request.form.get('reservation_open')
        values['notice'] = request.form.get('notice', '').strip()
        if values['reservation_open'] not in {'0', '1'} or len(values['notice']) > 255:
            raise RuleError('설정 값을 확인해 주세요.')
        with write_transaction():
            for key, value in values.items():
                setting = db.session.scalar(db.select(Setting).where(Setting.key == key))
                if setting is None:
                    db.session.add(Setting(key=key, value=str(value)))
                else:
                    setting.value = str(value)
            event(actor(), 'settings_update', 'settings')
        flash('설정을 저장했습니다. 기존 예약 시간은 유지되므로 예외 예약을 확인해 주세요.')
        return redirect(url_for('admin_dashboard'))

    @app.route('/admin/audit')
    @admin_required
    def admin_audit():
        events = db.paginate(db.select(AuditEvent).order_by(AuditEvent.id.desc()),
                             page=max(1, request.args.get('page', 1, type=int)), per_page=50, error_out=False)
        return render_template('admin_audit.html', events=events)
