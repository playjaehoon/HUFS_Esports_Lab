from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import check_password_hash
from models import db, Admin, Reservation, Setting, Student, BlockedTime
import os
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'super-secret-key-hufs-esports'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///esportslab.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

login_manager = LoginManager()
login_manager.login_view = 'student_login'
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    # Differentiate Admin and Student by prefix
    if user_id.startswith('admin_'):
        return Admin.query.get(int(user_id.split('_')[1]))
    elif user_id.startswith('student_'):
        return Student.query.get(int(user_id.split('_')[1]))
    return None

# Override get_id for Admin and Student inside models, but since models are already defined, 
# we'll patch it dynamically or handle it in login routes. 
# A cleaner way without changing models get_id is to monkeypatch them here:
Admin.get_id = lambda self: f"admin_{self.id}"
Student.get_id = lambda self: f"student_{self.id}"

def get_setting(key):
    s = Setting.query.filter_by(key=key).first()
    return s.value if s else None

@app.route('/')
@login_required
def index():
    if current_user.get_id().startswith('admin_'):
        return redirect(url_for('admin_dashboard'))
        
    notice = get_setting('notice')
    return render_template('index.html', notice=notice, student=current_user)

@app.route('/api/availability', methods=['GET'])
def get_availability():
    date = request.args.get('date')
    start_time = request.args.get('start_time', type=int)
    end_time = request.args.get('end_time', type=int)
    
    if not date or not start_time or not end_time:
        return jsonify({'error': 'Missing parameters'}), 400
        
    # Check if blocked by admin
    blocked_times = BlockedTime.query.filter_by(date=date).all()
    for bt in blocked_times:
        if bt.start_time is None and bt.end_time is None:
            return jsonify({'blocked': True, 'message': '해당 날짜는 관리자에 의해 예약이 제한되었습니다.'})
        # Specific time block overlap
        if max(bt.start_time, start_time) < min(bt.end_time, end_time):
            return jsonify({'blocked': True, 'message': '선택하신 시간 중 예약이 제한된 시간이 포함되어 있습니다.'})
            
    reservations = Reservation.query.filter_by(date=date, status='active').all()
    
    occupied_seats = set()
    for res in reservations:
        if max(res.start_time, start_time) < min(res.end_time, end_time):
            occupied_seats.add(res.seat_number)
            
    return jsonify({'occupied_seats': list(occupied_seats)})

@app.route('/api/reserve', methods=['POST'])
@login_required
def make_reservation():
    if not current_user.get_id().startswith('student_'):
        return jsonify({'success': False, 'message': '학생 계정으로 로그인해야 예약할 수 있습니다.'})

    res_open = get_setting('reservation_open')
    if res_open != '1':
        return jsonify({'success': False, 'message': '현재 예약 시스템이 비활성화 되어있습니다.'})
        
    data = request.json
    # Rely on session for student info, not client payload
    student_id = current_user.student_number
    student_name = current_user.name
    
    date = data.get('date')
    start_time = int(data.get('start_time'))
    end_time = int(data.get('end_time'))
    seat_number = int(data.get('seat_number'))
    
    # 0. Check for No-Show history (1 week ban)
    today_dt = datetime.now()
    today_str = today_dt.strftime('%Y-%m-%d')
    no_shows = Reservation.query.filter(
        Reservation.student_id == student_id,
        Reservation.status == 'active',
        Reservation.is_attended == False,
        Reservation.date < today_str
    ).all()
    
    for ns in no_shows:
        ns_date_dt = datetime.strptime(ns.date, '%Y-%m-%d')
        days_since = (today_dt - ns_date_dt).days
        if days_since <= 7:
            return jsonify({'success': False, 'message': '최근 1주일 이내 노쇼(No-show) 이력이 있어 예약을 하실 수 없습니다. (관리자 문의)'})
            
    max_hrs = int(get_setting('max_hours') or 3)
    
    # 0. Check BlockedTime
    blocked_times = BlockedTime.query.filter_by(date=date).all()
    for bt in blocked_times:
        if bt.start_time is None and bt.end_time is None:
            return jsonify({'success': False, 'message': '해당 날짜는 관리자에 의해 예약이 제한되었습니다.'})
        if max(bt.start_time, start_time) < min(bt.end_time, end_time):
            return jsonify({'success': False, 'message': '선택하신 시간 중 예약이 제한된 시간이 포함되어 있습니다.'})
            
    # 1. Check time duration logic
    duration = end_time - start_time
    if duration <= 0:
        return jsonify({'success': False, 'message': '예약 종료 시간이 시작 시간보다 빨라야 합니다.'})
    if duration > max_hrs:
        return jsonify({'success': False, 'message': f'한 번에 최대 {max_hrs}시간까지만 예약할 수 있습니다.'})
        
    # 2. Check if student already has a reservation today (1 per day limit)
    student_reservations = Reservation.query.filter_by(
        student_id=student_id, date=date, status='active'
    ).all()
    
    if len(student_reservations) > 0:
        return jsonify({'success': False, 'message': '하루에 한 좌석(예약 1건)까지만 예약할 수 있습니다.'})
        
    # 3. Check seat availability
    overlapping = Reservation.query.filter(
        Reservation.date == date,
        Reservation.seat_number == seat_number,
        Reservation.status == 'active'
    ).all()
    
    for res in overlapping:
        if max(res.start_time, start_time) < min(res.end_time, end_time):
            return jsonify({'success': False, 'message': '선택하신 좌석은 해당 시간에 이미 예약되었습니다.'})
            
    new_res = Reservation(
        student_id=student_id,
        student_name=student_name,
        date=date,
        start_time=start_time,
        end_time=end_time,
        seat_number=seat_number
    )
    db.session.add(new_res)
    db.session.commit()
    
    return jsonify({'success': True, 'message': '예약이 성공적으로 완료되었습니다.'})

from werkzeug.security import generate_password_hash

@app.route('/login', methods=['GET', 'POST'])
def student_login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        student_number = request.form.get('student_number')
        password = request.form.get('password')
        
        student = Student.query.filter_by(student_number=student_number).first()
        
        # If student exists, check password
        if student:
            if check_password_hash(student.password_hash, password):
                # Check if student is blocked
                from datetime import datetime
                if student.blocked_until and student.blocked_until > datetime.now():
                    if student.blocked_until.year > 2900:
                        flash('관리자에 의해 영구 정지된 계정입니다.')
                    else:
                        flash(f'관리자에 의해 {student.blocked_until.strftime("%Y-%m-%d %H:%M")}까지 이용이 정지되었습니다.')
                    return render_template('student_login.html')
                
                # Check if student is approved 
                if not student.is_approved:
                    return render_template('student_login.html', pending=True)
                
                login_user(student)
                return redirect(url_for('index'))
            else:
                flash('비밀번호가 틀렸습니다.')
        else:
            flash('가입되지 않은 학번입니다. 먼저 회원가입을 진행해주세요.')
            
    registered = request.args.get('registered')
    return render_template('student_login.html', registered=registered)

@app.route('/register', methods=['GET', 'POST'])
def student_register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        student_number = request.form.get('student_number')
        name = request.form.get('name')
        password = request.form.get('password')
        
        # Check if already exists
        if Student.query.filter_by(student_number=student_number).first():
            flash('이미 가입된 학번입니다.')
            return render_template('student_register.html')
            
        new_student = Student(
            student_number=student_number,
            name=name,
            password_hash=generate_password_hash(password),
            pin_plain=password,
            is_approved=False
        )
        db.session.add(new_student)
        db.session.commit()
        
        return redirect(url_for('student_login', registered=1))
        
    return render_template('student_register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('student_login'))

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if current_user.is_authenticated:
        return redirect(url_for('admin_dashboard'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        admin = Admin.query.filter_by(username=username).first()
        if admin and check_password_hash(admin.password_hash, password):
            login_user(admin)
            return redirect(url_for('admin_dashboard'))
        flash('아이디 또는 비밀번호가 틀렸습니다.')
        
    return render_template('admin_login.html')

@app.route('/admin/logout')
@login_required
def admin_logout():
    logout_user()
    return redirect(url_for('admin_login'))

from datetime import datetime

@app.route('/admin', methods=['GET'])
@login_required
def admin_dashboard():
    # String representation of today in local timezone
    today_str = datetime.now().strftime('%Y-%m-%d')
    
    # Active reservations >= today
    active_reservations = Reservation.query.filter(
        Reservation.status == 'active',
        Reservation.date >= today_str
    ).order_by(Reservation.date.asc(), Reservation.start_time.asc()).all()
    
    # Past reservations < today
    past_query = Reservation.query.filter(
        Reservation.status == 'active',
        Reservation.date < today_str
    ).order_by(Reservation.date.desc(), Reservation.start_time.desc())
    
    # Process months for dropdown
    all_past = past_query.all()
    available_months = sorted(list(set([r.date[:7] for r in all_past])), reverse=True)
    
    selected_month = request.args.get('month')
    if selected_month and selected_month in available_months:
        past_query = past_query.filter(Reservation.date.startswith(selected_month))
        
    past_reservations = past_query.all()
    
    blocked_times = BlockedTime.query.order_by(BlockedTime.date.asc()).all()
    
    res_open = get_setting('reservation_open')
    max_hours = get_setting('max_hours')
    notice = get_setting('notice')
    
    return render_template('admin_dashboard.html', 
                          active_reservations=active_reservations, 
                          past_reservations=past_reservations,
                          blocked_times=blocked_times,
                          available_months=available_months,
                          selected_month=selected_month,
                          res_open=res_open, 
                          max_hours=max_hours,
                          notice=notice)

@app.route('/admin/students', methods=['GET'])
@login_required
def admin_students():
    from datetime import datetime
    all_students = Student.query.order_by(Student.student_number.asc()).all()
    now = datetime.now()
    pending_students = []
    active_students = []
    suspended_students = []
    
    for s in all_students:
        if not s.is_approved:
            pending_students.append(s)
        elif s.blocked_until and s.blocked_until > now:
            suspended_students.append(s)
        else:
            active_students.append(s)
    
    return render_template('admin_students.html', 
                           pending_students=pending_students,
                           active_students=active_students,
                           suspended_students=suspended_students)

@app.route('/admin/students/approve/<int:student_id>', methods=['POST'])
@login_required
def admin_approve_student(student_id):
    student = Student.query.get_or_404(student_id)
    student.is_approved = True
    db.session.commit()
    flash(f'{student.name} 학생의 가입을 승인했습니다.')
    return redirect(url_for('admin_students'))

@app.route('/admin/students/delete/<int:student_id>', methods=['POST'])
@login_required
def admin_delete_student(student_id):
    student = Student.query.get_or_404(student_id)
    
    # Optionally: also cancel all their active reservations? 
    # Or just delete their account so they can't log in again.
    
    db.session.delete(student)
    db.session.commit()
    flash('해당 학생 계정이 삭제되었습니다.')
    return redirect(url_for('admin_students'))

from datetime import timedelta

@app.route('/admin/students/block/<int:student_id>', methods=['POST'])
@login_required
def admin_block_student(student_id):
    student = Student.query.get_or_404(student_id)
    duration = request.form.get('duration')
    
    if duration == '1week':
        student.blocked_until = datetime.now() + timedelta(days=7)
        flash(f"{student.name} 학생이 1주일간 정지되었습니다.")
    elif duration == '2weeks':
        student.blocked_until = datetime.now() + timedelta(days=14)
        flash(f"{student.name} 학생이 2주일간 정지되었습니다.")
    elif duration == 'permanent':
        student.blocked_until = datetime.now() + timedelta(days=36500) # Roughly 100 years
        flash(f"{student.name} 학생이 영구 정지되었습니다.")
    elif duration == 'unblock':
        student.blocked_until = None
        flash(f"{student.name} 학생의 정지가 해제되었습니다.")
        
    db.session.commit()
    return redirect(url_for('admin_students'))

@app.route('/admin/block', methods=['POST'])
@login_required
def admin_block_time():
    date = request.form.get('date')
    block_type = request.form.get('block_type') # 'all' or 'specific'
    
    if block_type == 'all':
        new_block = BlockedTime(date=date, start_time=None, end_time=None)
    else:
        start_time = request.form.get('start_time', type=int)
        end_time = request.form.get('end_time', type=int)
        new_block = BlockedTime(date=date, start_time=start_time, end_time=end_time)
        
    db.session.add(new_block)
    db.session.commit()
    flash('예약 제한이 설정되었습니다.')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/unblock/<int:block_id>', methods=['POST'])
@login_required
def admin_unblock_time(block_id):
    bt = BlockedTime.query.get_or_404(block_id)
    db.session.delete(bt)
    db.session.commit()
    flash('예약 제한이 해제되었습니다.')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/cancel/<int:reservation_id>', methods=['POST'])
@login_required
def admin_cancel_reservation(reservation_id):
    res = Reservation.query.get_or_404(reservation_id)
    res.status = 'cancelled'
    db.session.commit()
    flash('예약이 취소되었습니다.')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/attend/<int:reservation_id>', methods=['POST'])
@login_required
def admin_attend_reservation(reservation_id):
    res = Reservation.query.get_or_404(reservation_id)
    res.is_attended = True
    res.status = 'active' # Un-cancel if it was cancelled
    db.session.commit()
    flash('방문 확인이 완료되었습니다.')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/unattend/<int:reservation_id>', methods=['POST'])
@login_required
def admin_unattend_reservation(reservation_id):
    res = Reservation.query.get_or_404(reservation_id)
    res.is_attended = False
    db.session.commit()
    flash('방문 확인이 취소되었습니다.')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/settings', methods=['POST'])
@login_required
def admin_settings():
    res_open = request.form.get('reservation_open', '0')
    max_hours = request.form.get('max_hours', '3')
    notice = request.form.get('notice', '')
    
    # Update settings
    Setting.query.filter_by(key='reservation_open').update({'value': res_open})
    Setting.query.filter_by(key='max_hours').update({'value': max_hours})
    Setting.query.filter_by(key='notice').update({'value': notice})
    
    db.session.commit()
    flash('설정이 저장되었습니다.')
    return redirect(url_for('admin_dashboard'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)
