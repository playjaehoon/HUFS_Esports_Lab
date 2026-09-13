from datetime import datetime
from zoneinfo import ZoneInfo
import re
import pytest
from werkzeug.security import generate_password_hash
from application import create_app
from booking import DEFAULTS
from models import Admin, Student, Setting, StudentNumberClaim, db

PASSWORD = 'local-test-password-2026'


@pytest.fixture(scope='session')
def password_hash():
    return generate_password_hash(PASSWORD)


@pytest.fixture
def app(tmp_path, password_hash):
    app = create_app({'TESTING': True, 'SECRET_KEY': 'isolated-test-key-with-more-than-32-characters',
                      'SQLALCHEMY_DATABASE_URI': f'sqlite:///{(tmp_path / "test.db").as_posix()}',
                      'SESSION_COOKIE_SECURE': False, 'AUTH_RATE_LIMIT_ENABLED': False,
                      'NOW_PROVIDER': lambda: datetime(2026, 9, 14, 8, tzinfo=ZoneInfo('Asia/Seoul'))})
    with app.app_context():
        db.create_all()
        db.session.add_all([Setting(key=k, value=v) for k, v in DEFAULTS.items()])
        db.session.add(Admin(id=1, username='staff', password_hash=password_hash))
        db.session.add_all([Student(id=i, student_number=f'20260000{i}', name=f'Test student {i}', password_hash=password_hash) for i in (1, 2)])
        db.session.flush()
        db.session.add_all([StudentNumberClaim(student_number=f'20260000{i}',student_pk=i) for i in (1,2)])
        db.session.commit()
    yield app
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


def csrf(client, path='/login'):
    response = client.get(path, follow_redirects=True)
    match = re.search(r'name="csrf-token" content="([^"]+)"', response.get_data(as_text=True))
    assert match, response.get_data(as_text=True)
    return match.group(1)


def post(client, path, data=None, json=None):
    token = csrf(client)
    if json is not None:
        return client.post(path, json=json, headers={'X-CSRFToken': token})
    return client.post(path, data={**(data or {}), 'csrf_token': token})


def login(app, student=1, admin=False):
    client = app.test_client()
    path = '/admin/login' if admin else '/login'
    data = {'username': 'staff'} if admin else {'student_number': f'20260000{student}'}
    response = post(client, path, {**data, 'password': PASSWORD})
    assert response.status_code == 302
    return client


def booking(**overrides):
    return {'date': '2026-09-15', 'start_time': 10, 'end_time': 12, 'seat_number': 1, **overrides}


def reserve(client, **overrides):
    response = post(client, '/api/reserve', json=booking(**overrides))
    assert response.status_code == 201, response.get_json()
    return int(response.get_json()['redirect_url'].rsplit('/', 1)[1])
