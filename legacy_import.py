"""Non-destructive import of a verified legacy SQLite snapshot into a new DB.

The source is read-only. Unexpected schema/data and conflicting reservations
stop the import. Only a fully validated destination is published.
"""
from contextlib import closing
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
import tempfile
from zoneinfo import ZoneInfo

from flask import current_app
from flask_migrate import upgrade
from sqlalchemy import text

from booking import DEFAULTS, SEATS, parse_date
from models import (Admin, AuditEvent, BlockedTime, DailyBooking, Reservation,
                    ReservationSlot, Setting, Student, StudentNumberClaim, db)

LEGACY_COLUMNS = {
    'admin': {'id', 'username', 'password_hash'},
    'student': {'id', 'student_number', 'name', 'password_hash', 'pin_plain', 'blocked_until', 'is_approved'},
    'reservation': {'id', 'student_id', 'student_name', 'date', 'start_time', 'end_time', 'seat_number', 'status', 'is_attended', 'created_at'},
    'blocked_time': {'id', 'date', 'start_time', 'end_time'},
    'setting': {'id', 'key', 'value'},
}


def load_snapshot(source):
    with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute('BEGIN')
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        if 'alembic_version' in tables and connection.execute('SELECT count(*) FROM alembic_version').fetchone()[0] == 0:
            tables.remove('alembic_version')
        if tables != set(LEGACY_COLUMNS):
            raise ValueError('Expected legacy tables do not match. Inspect the server schema before importing.')
        data = {}
        for table, allowed in LEGACY_COLUMNS.items():
            columns = {row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')}
            required = allowed - ({'pin_plain', 'is_approved'} if table == 'student' else set())
            if columns - allowed or not required.issubset(columns):
                raise ValueError(f'Unexpected schema in {table}. No data was imported.')
            # Never select plaintext credentials, even into the importer process.
            selected = sorted(columns - {'pin_plain', 'is_approved'})
            projection = ','.join(f'"{column}"' for column in selected)
            data[table] = [dict(row) for row in connection.execute(f'SELECT {projection} FROM "{table}"')]
        if connection.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Legacy database integrity check failed.')
        return data


def import_legacy(source, output, legacy_timezone):
    source, output = Path(source).resolve(), Path(output).resolve()
    if not source.is_file() or output.exists() or not output.parent.is_dir():
        raise ValueError('Source must exist; output must be a new file in an existing directory.')
    if legacy_timezone not in {'Asia/Seoul', 'UTC'}:
        raise ValueError('Specify the original server timezone explicitly.')
    data = load_snapshot(source)
    owners = {s['student_number']: s['id'] for s in data['student']}
    if len(owners) != len(data['student']):
        raise ValueError('Duplicate student numbers require manual review.')
    occupied, days = set(), set()
    for row in data['reservation']:
        parse_date(row['date'])
        if row['student_id'] not in owners:
            raise ValueError(f"Reservation ID {row['id']} has no student. Resolve ownership before import.")
        if row['status'] not in {'active', 'cancelled'} or not 0 <= row['start_time'] < row['end_time'] <= 24 or row['seat_number'] not in SEATS:
            raise ValueError(f"Reservation ID {row['id']} has invalid fields.")
        if row['status'] == 'active':
            day = (owners[row['student_id']], row['date'])
            slots = {(row['date'], row['seat_number'], h) for h in range(row['start_time'], row['end_time'])}
            if day in days or occupied & slots:
                raise ValueError(f"Reservation ID {row['id']} conflicts with another booking. Resolve before import.")
            days.add(day)
            occupied.update(slots)
    for row in data['blocked_time']:
        parse_date(row['date'])
        a, b = row['start_time'], row['end_time']
        if (a is None) != (b is None) or (a is not None and not 0 <= a < b <= 24):
            raise ValueError(f"Blocked time ID {row['id']} is invalid.")
        for reservation in data['reservation']:
            if reservation['status'] == 'active' and reservation['date'] == row['date']:
                if a is None or max(a, reservation['start_time']) < min(b, reservation['end_time']):
                    raise ValueError(f"Reservation ID {reservation['id']} conflicts with blocked time ID {row['id']}.")
    values = dict(DEFAULTS)
    values.update({s['key']: s['value'] for s in data['setting']})
    try:
        opening, closing = int(values['open_hour']), int(values['close_hour'])
        valid = (values['reservation_open'] in {'0', '1'} and 0 <= opening < closing <= 24
                 and 1 <= int(values['max_hours']) <= closing - opening and 0 <= int(values['advance_days']) <= 60)
    except (TypeError, ValueError):
        valid = False
    if not valid:
        raise ValueError('Legacy operating settings need review.')

    from application import create_app
    secret = current_app.secret_key
    migration_directory = str(Path(__file__).with_name('migrations'))
    with tempfile.TemporaryDirectory(prefix='hufs-import-', dir=output.parent) as temporary:
        new_file = Path(temporary) / 'upgraded.db'
        target = create_app({'SECRET_KEY': secret, 'SQLALCHEMY_DATABASE_URI': f'sqlite:///{new_file.as_posix()}'})
        with target.app_context():
            try:
                upgrade(directory=migration_directory)
                for row in data['admin']:
                    db.session.add(Admin(**row))
                for row in data['student']:
                    blocked = row['blocked_until']
                    if blocked:
                        row['blocked_until'] = datetime.fromisoformat(blocked).replace(tzinfo=ZoneInfo(legacy_timezone)).astimezone(timezone.utc).replace(tzinfo=None)
                    db.session.add(Student(**row, must_change_password=True))
                db.session.flush()
                db.session.add_all([StudentNumberClaim(student_number=row['student_number'], student_pk=row['id'])
                                    for row in data['student']])
                for row in data['reservation']:
                    row['created_at'] = datetime.fromisoformat(row['created_at']) if row['created_at'] else datetime.now(timezone.utc).replace(tzinfo=None)
                    row['is_attended'] = bool(row['is_attended'])
                    reservation = Reservation(**row, student_pk=owners[row['student_id']])
                    db.session.add(reservation)
                    db.session.flush()
                    if reservation.status == 'active':
                        db.session.add(DailyBooking(student_pk=reservation.student_pk, date=reservation.date, reservation_id=reservation.id))
                        for hour in range(reservation.start_time, reservation.end_time):
                            db.session.add(ReservationSlot(reservation_id=reservation.id, date=reservation.date, seat_number=reservation.seat_number, hour=hour))
                for row in data['blocked_time']:
                    db.session.add(BlockedTime(**row, reason='이전 운영 설정'))
                for key, value in values.items():
                    setting = db.session.scalar(db.select(Setting).where(Setting.key == key))
                    if setting:
                        setting.value = value
                    else:
                        db.session.add(Setting(key=key, value=value))
                db.session.add(AuditEvent(actor='server-cli', action='legacy_import', target='database', reason='Read-only source; new database'))
                db.session.commit()
                for model, table in [(Admin, 'admin'), (Student, 'student'), (Reservation, 'reservation'), (BlockedTime, 'blocked_time')]:
                    if db.session.scalar(db.select(db.func.count()).select_from(model)) != len(data[table]):
                        raise RuntimeError('Imported row count mismatch.')
                if db.session.execute(text('PRAGMA integrity_check')).scalar() != 'ok' or db.session.execute(text('PRAGMA foreign_key_check')).first():
                    raise RuntimeError('Destination integrity check failed.')
            finally:
                db.session.remove()
                db.engine.dispose()
        # Same filesystem, atomic publication, refuses an existing destination.
        os.link(new_file, output)
    return {table: len(rows) for table, rows in data.items()}
