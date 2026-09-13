"""Exercise real Alembic revisions and import publication with synthetic SQLite data."""
from contextlib import closing, contextmanager
from datetime import datetime
from pathlib import Path
import sqlite3

import pytest

from application import create_app
from legacy_import import import_legacy
from models import db


MIGRATIONS = str(Path(__file__).resolve().parents[1] / 'migrations')
PLAINTEXT_PIN = '849372'


@contextmanager
def migration_app(database):
    app = create_app({
        'TESTING': True,
        'SECRET_KEY': 'migration-tests-only-secret-longer-than-32-characters',
        'SQLALCHEMY_DATABASE_URI': f'sqlite:///{database.as_posix()}',
        'SESSION_COOKIE_SECURE': False,
        'AUTH_RATE_LIMIT_ENABLED': False,
    })
    try:
        yield app
    finally:
        with app.app_context():
            db.session.remove()
            db.engine.dispose()


def upgrade(app, revision='head'):
    return app.test_cli_runner().invoke(args=['db', 'upgrade', '--directory', MIGRATIONS, revision])


def rows(database, query, parameters=()):
    with closing(sqlite3.connect(database)) as connection:
        return connection.execute(query, parameters).fetchall()


def change(database, query, parameters=()):
    with closing(sqlite3.connect(database)) as connection:
        connection.execute(query, parameters)
        connection.commit()


@pytest.fixture
def legacy(tmp_path, password_hash):
    """IDs deliberately differ from row positions and contain approved/waiting users."""
    source = tmp_path / 'legacy.db'
    with closing(sqlite3.connect(source)) as connection:
        connection.executescript('''
            CREATE TABLE admin (
                id INTEGER PRIMARY KEY, username VARCHAR(50) NOT NULL UNIQUE,
                password_hash VARCHAR(255) NOT NULL);
            CREATE TABLE student (
                id INTEGER PRIMARY KEY, student_number VARCHAR(9) NOT NULL UNIQUE,
                name VARCHAR(50) NOT NULL, password_hash VARCHAR(255) NOT NULL,
                pin_plain VARCHAR(10), blocked_until DATETIME, is_approved BOOLEAN);
            CREATE TABLE reservation (
                id INTEGER PRIMARY KEY, student_id VARCHAR(20) NOT NULL,
                student_name VARCHAR(50) NOT NULL, date VARCHAR(10) NOT NULL,
                start_time INTEGER NOT NULL, end_time INTEGER NOT NULL,
                seat_number INTEGER NOT NULL, status VARCHAR(20) NOT NULL,
                is_attended BOOLEAN, created_at DATETIME);
            CREATE TABLE blocked_time (
                id INTEGER PRIMARY KEY, date VARCHAR(10) NOT NULL,
                start_time INTEGER, end_time INTEGER);
            CREATE TABLE setting (
                id INTEGER PRIMARY KEY, key VARCHAR(50) NOT NULL UNIQUE,
                value VARCHAR(255) NOT NULL);
        ''')
        connection.execute('INSERT INTO admin VALUES (7, ?, ?)', ('test-staff', password_hash))
        connection.executemany('INSERT INTO student VALUES (?, ?, ?, ?, ?, ?, ?)', [
            (3, '202600003', 'Synthetic waiting', password_hash, PLAINTEXT_PIN,
             '2026-10-04 09:30:00.000000', 0),
            (8, '202600008', 'Synthetic approved', password_hash, PLAINTEXT_PIN, None, 1),
        ])
        connection.executemany('INSERT INTO reservation VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', [
            (11, '202600003', 'Booking snapshot A', '2026-10-01', 10, 12, 4, 'active', 0,
             '2026-09-25 01:02:03.000000'),
            (12, '202600008', 'Cancelled snapshot', '2026-10-01', 10, 12, 4, 'cancelled', 0,
             '2026-09-25 02:03:04.000000'),
            (13, '202600008', 'Historical snapshot', '2026-08-10', 13, 15, 5, 'active', 1,
             '2026-08-09 03:04:05.000000'),
        ])
        connection.execute('INSERT INTO blocked_time VALUES (9, ?, NULL, NULL)', ('2026-10-02',))
        connection.executemany('INSERT INTO setting VALUES (?, ?, ?)', [
            (1, 'max_hours', '2'), (2, 'notice', 'Synthetic notice'),
        ])
        connection.commit()
    return source


@pytest.mark.parametrize('legacy_timezone,expected_block', [
    ('Asia/Seoul', datetime(2026, 10, 4, 0, 30)),
    ('UTC', datetime(2026, 10, 4, 9, 30)),
])
def test_import_preserves_source_and_converts_security_and_relations(
        legacy, tmp_path, password_hash, legacy_timezone, expected_block):
    before = legacy.read_bytes()
    output = tmp_path / 'imported.db'
    with migration_app(tmp_path / 'cli.db') as app, app.app_context():
        result = import_legacy(legacy, output, legacy_timezone)
    assert legacy.read_bytes() == before
    assert result == {'admin': 1, 'student': 2, 'reservation': 3, 'blocked_time': 1, 'setting': 2}
    assert output.is_file()
    assert PLAINTEXT_PIN.encode() not in output.read_bytes()
    columns = {row[1] for row in rows(output, 'PRAGMA table_info(student)')}
    assert not {'pin_plain', 'is_approved'} & columns
    students = rows(output, 'SELECT id, password_hash, must_change_password, blocked_until FROM student ORDER BY id')
    assert [(s[0], s[1], s[2]) for s in students] == [(3, password_hash, 1), (8, password_hash, 1)]
    assert datetime.fromisoformat(students[0][3]) == expected_block
    assert students[1][3] is None
    assert rows(output, 'SELECT student_number, student_pk FROM student_number_claim ORDER BY student_pk') == [
        ('202600003', 3), ('202600008', 8)]
    assert rows(output, 'SELECT id, student_pk, student_name, status FROM reservation ORDER BY id') == [
        (11, 3, 'Booking snapshot A', 'active'),
        (12, 8, 'Cancelled snapshot', 'cancelled'),
        (13, 8, 'Historical snapshot', 'active'),
    ]
    # created_at was UTC in the original model, regardless of the server timezone.
    assert datetime.fromisoformat(rows(output, 'SELECT created_at FROM reservation WHERE id=11')[0][0]) == datetime(2026, 9, 25, 1, 2, 3)
    assert rows(output, 'SELECT reservation_id, student_pk FROM daily_booking ORDER BY reservation_id') == [(11, 3), (13, 8)]
    assert rows(output, 'SELECT reservation_id, hour FROM reservation_slot ORDER BY reservation_id, hour') == [(11, 10), (11, 11), (13, 13), (13, 14)]
    assert rows(output, 'SELECT value FROM setting WHERE key="max_hours"') == [('2',)]
    assert rows(output, 'SELECT value FROM setting WHERE key="open_hour"') == [('9',)]
    assert rows(output, 'SELECT action FROM audit_event') == [('legacy_import',)]
    assert rows(output, 'SELECT version_num FROM alembic_version') == [('0002',)]
    assert rows(output, 'PRAGMA integrity_check') == [('ok',)]
    assert rows(output, 'PRAGMA foreign_key_check') == []
    with closing(sqlite3.connect(output)) as connection:
        connection.execute('PRAGMA foreign_keys=ON')
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute('INSERT INTO student_number_claim VALUES (?, ?)', ('202699999', 999))
    assert not list(tmp_path.glob('hufs-import-*'))


@pytest.mark.parametrize('mutation,message', [
    ("UPDATE reservation SET status='active' WHERE id=12", 'conflicts with another booking'),
    ("UPDATE reservation SET student_id='202600003', date='2026-10-01' WHERE id=13", 'conflicts with another booking'),
    ('UPDATE reservation SET seat_number=999 WHERE id=11', 'invalid fields'),
    ("UPDATE blocked_time SET date='2026-10-01' WHERE id=9", 'conflicts with blocked time'),
    ("UPDATE reservation SET student_id='202699999' WHERE id=11", 'has no student'),
])
def test_rejected_import_never_publishes_or_changes_source(legacy, tmp_path, mutation, message):
    change(legacy, mutation)
    before = legacy.read_bytes()
    output = tmp_path / 'rejected.db'
    with migration_app(tmp_path / 'cli.db') as app, app.app_context():
        with pytest.raises(ValueError, match=message):
            import_legacy(legacy, output, 'Asia/Seoul')
    assert legacy.read_bytes() == before
    assert not output.exists()
    assert not list(tmp_path.glob('hufs-import-*'))


def test_import_does_not_overwrite_existing_destination(legacy, tmp_path):
    output = tmp_path / 'existing.db'
    output.write_bytes(b'existing-destination-must-survive')
    before = legacy.read_bytes()
    with migration_app(tmp_path / 'cli.db') as app, app.app_context():
        with pytest.raises(ValueError, match='output must be a new file'):
            import_legacy(legacy, output, 'UTC')
    assert output.read_bytes() == b'existing-destination-must-survive'
    assert legacy.read_bytes() == before


def test_direct_legacy_upgrade_is_refused_without_even_creating_version_table(legacy):
    before = legacy.read_bytes()
    with migration_app(legacy) as app:
        result = upgrade(app)
        assert result.exit_code != 0
        assert 'import-legacy' in result.output
    assert legacy.read_bytes() == before
    assert rows(legacy, "SELECT name FROM sqlite_master WHERE name='alembic_version'") == []


def test_empty_version_table_from_older_failed_upgrade_can_be_imported(legacy, tmp_path):
    change(legacy, 'CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)')
    before = legacy.read_bytes()
    output = tmp_path / 'imported.db'
    with migration_app(tmp_path / 'cli.db') as app, app.app_context():
        import_legacy(legacy, output, 'UTC')
    assert legacy.read_bytes() == before
    assert rows(output, 'SELECT version_num FROM alembic_version') == [('0002',)]


def test_fresh_upgrade_is_versioned_and_safe_to_repeat(tmp_path):
    database = tmp_path / 'fresh.db'
    with migration_app(database) as app:
        result = upgrade(app)
        assert result.exit_code == 0, result.output
        assert rows(database, 'SELECT version_num FROM alembic_version') == [('0002',)]
        result = upgrade(app)
        assert result.exit_code == 0, result.output
    assert rows(database, 'SELECT version_num FROM alembic_version') == [('0002',)]
    assert rows(database, 'PRAGMA integrity_check') == [('ok',)]


def test_revision_0002_backfills_number_ownership_from_0001(tmp_path, password_hash):
    database = tmp_path / 'revision-0001.db'
    with migration_app(database) as app:
        result = upgrade(app, '0001')
        assert result.exit_code == 0, result.output
        change(database, '''INSERT INTO student
            (id, student_number, name, password_hash, blocked_until, archived, must_change_password, session_version)
            VALUES (42, '202600042', 'Synthetic existing student', ?, NULL, 0, 0, 1)''', (password_hash,))
        result = upgrade(app)
        assert result.exit_code == 0, result.output
        assert rows(database, 'SELECT student_number, student_pk FROM student_number_claim') == [('202600042', 42)]
        assert rows(database, 'SELECT name, password_hash FROM student WHERE id=42') == [('Synthetic existing student', password_hash)]
        result = upgrade(app)
        assert result.exit_code == 0, result.output
    assert rows(database, 'SELECT student_number, student_pk FROM student_number_claim') == [('202600042', 42)]
    assert rows(database, 'PRAGMA foreign_key_check') == []
