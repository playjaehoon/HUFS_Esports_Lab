"""Contact entry, ownership and visibility use isolated synthetic members."""
import pytest
from conftest import PASSWORD, booking, login, post
from models import AuditEvent, Student, db, utcnow


def signup(phone):
    return {'student_number': '202699999', 'name': 'Contact test', 'department': '철학과',
            'phone': phone, 'password': PASSWORD, 'password_confirm': PASSWORD}


@pytest.mark.parametrize('phone, expected', [
    ('010-0000-0001', '01000000001'), ('02 000 0001', '020000001'),
    ('+1 202-555-0100', '+12025550100'),
])
def test_signup_stores_contact_and_only_owner_and_staff_can_see_it(app, phone, expected):
    student = app.test_client()
    assert post(student, '/register', signup(phone)).status_code == 302
    with app.app_context():
        user = db.session.scalar(db.select(Student).where(Student.student_number == '202699999'))
        assert user.phone == expected
        audit_text = str([(row.action, row.reason) for row in db.session.scalars(db.select(AuditEvent))])
        assert expected not in audit_text and phone not in audit_text
    assert expected in student.get('/account').get_data(as_text=True)
    admin = login(app, admin=True)
    assert f'href="tel:{expected}"' in admin.get('/admin/students').get_data(as_text=True)
    visitor = app.test_client()
    for path in ['/', '/api/lab/calendar?month=2026-09', '/api/lab/status']:
        assert expected not in visitor.get(path).get_data(as_text=True)
    other = login(app)
    assert expected not in other.get('/account').get_data(as_text=True)
    assert other.get('/admin/students').status_code == 403


@pytest.mark.parametrize('phone', ['', '   ', '123', 'phone', '010-0000-0001<script>',
                                    '++12025550100', '1' * 33])
def test_invalid_contact_rejects_signup_without_creating_account(app, phone):
    response = post(app.test_client(), '/register', signup(phone))
    assert response.status_code == 400 and '전화번호' in response.get_data(as_text=True)
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(Student)) == 2


def test_existing_member_can_book_but_must_add_contact_on_profile_save(app):
    student = login(app)
    assert student.get('/account').status_code == 200
    assert post(student, '/api/reserve', json=booking()).status_code == 201
    profile = {'student_number': '202600001', 'name': 'Test student 1', 'department': '철학과',
               'current_password': PASSWORD}
    assert post(student, '/account', profile).status_code == 400
    with app.app_context():
        assert db.session.get(Student, 1).phone is None
        assert db.session.get(Student, 1).department is None
    assert post(student, '/account', {**profile, 'phone': '010-0000-0001'}).status_code == 302
    with app.app_context():
        user = db.session.get(Student, 1)
        verified = utcnow()
        user.identity_verified_at, user.identity_verified_by = verified, 1
        db.session.commit()
    # Phone correction is not a student-card identity change.
    assert post(student, '/account', {**profile, 'phone': '010-0000-0002'}).status_code == 302
    with app.app_context():
        assert db.session.get(Student, 1).phone == '01000000002'
        assert db.session.get(Student, 1).identity_verified_at == verified
        assert db.session.get(Student, 2).phone is None
    assert post(student, '/account', {**profile, 'phone': 'invalid'}).status_code == 400
    with app.app_context():
        assert db.session.get(Student, 1).phone == '01000000002'
