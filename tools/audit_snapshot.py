"""Offline characterization of the initial repository, using synthetic data only.

Run from a local checkout: python tools/audit_snapshot.py
The app is copied into a temporary directory before import. No HTTP server or
production database is used. This records existing behavior, not release tests.
"""

import importlib
import importlib.metadata
import json
from pathlib import Path
import secrets
import shutil
import sys
import tempfile
from datetime import datetime, timedelta


def main():
    source = Path(__file__).resolve().parents[1]
    results = []
    with tempfile.TemporaryDirectory(prefix="hufs-offline-audit-") as folder:
        copied = Path(folder)
        for filename in ("app.py", "models.py"):
            shutil.copy2(source / filename, copied / filename)
        shutil.copytree(source / "templates", copied / "templates")
        sys.path.insert(0, str(copied))
        module = importlib.import_module("app")
        app, db = module.app, module.db
        models = importlib.import_module("models")
        from werkzeug.security import generate_password_hash

        app.config.update(TESTING=False, PROPAGATE_EXCEPTIONS=False)
        app.logger.disabled = True
        today = datetime.now().date()
        tomorrow = (today + timedelta(days=1)).isoformat()
        password = secrets.token_hex(8)
        password_hash = generate_password_hash(password)
        sequence = 0

        def record(name, **values):
            results.append({"check": name, **values})

        with app.app_context():
            assert Path(db.engine.url.database).resolve().is_relative_to(copied)
            db.create_all()
            db.session.add_all([
                models.Setting(key="reservation_open", value="1"),
                models.Setting(key="max_hours", value="3"),
                models.Setting(key="notice", value="Offline audit"),
            ])
            db.session.commit()

        def student_client():
            nonlocal sequence
            sequence += 1
            number = str(900000000 + sequence)
            with app.app_context():
                student = models.Student(student_number=number, name="AUDIT ONLY",
                                         password_hash=password_hash,
                                         pin_plain=password, is_approved=True)
                db.session.add(student)
                db.session.commit()
                student_pk = student.id
            client = app.test_client()
            response = client.post("/login", data={"student_number": number,
                                                   "password": password})
            assert response.status_code == 302
            return client, number, student_pk

        def payload(**overrides):
            return {"date": tomorrow, "start_time": 10, "end_time": 12,
                    "seat_number": 1, **overrides}

        client, _, _ = student_client()
        record("anonymous_admin", status=app.test_client().get("/admin").status_code)
        record("student_reads_admin", status=client.get("/admin").status_code)
        response = client.get("/admin/students")
        record("student_reads_student_list", status=response.status_code,
               synthetic_pin_visible=password in response.get_data(as_text=True))
        response = client.post("/admin/settings", data={"reservation_open": "1",
                               "max_hours": "3", "notice": "Changed by student"})
        with app.app_context():
            changed = models.Setting.query.filter_by(key="notice").first().value
        record("student_changes_admin_settings", status=response.status_code,
               changed=changed == "Changed by student")

        owner, owner_number, _ = student_client()
        owner.post("/api/reserve", json=payload(seat_number=2))
        with app.app_context():
            reservation_id = models.Reservation.query.filter_by(student_id=owner_number).first().id
        response = client.post(f"/admin/cancel/{reservation_id}")
        with app.app_context():
            cancelled = db.session.get(models.Reservation, reservation_id).status == "cancelled"
        record("student_cancels_other_reservation", status=response.status_code, cancelled=cancelled)
        response = client.post(f"/admin/attend/{reservation_id}")
        with app.app_context():
            reservation = db.session.get(models.Reservation, reservation_id)
            record("student_attends_cancelled_future_reservation", status=response.status_code,
                   active=reservation.status == "active", attended=reservation.is_attended)

        cases = {
            "past_date_accepted": payload(date=(today - timedelta(days=30)).isoformat()),
            "beyond_seven_days_accepted": payload(date=(today + timedelta(days=60)).isoformat()),
            "outside_hours_accepted": payload(start_time=2, end_time=4),
            "nonexistent_seat_accepted": payload(seat_number=999),
            "missing_times": {"date": tomorrow, "seat_number": 1},
        }
        for name, data in cases.items():
            test_client, _, _ = student_client()
            response = test_client.post("/api/reserve", json=data)
            record(name, status=response.status_code, body=response.get_json(silent=True))

        blocked_client, _, blocked_id = student_client()
        with app.app_context():
            db.session.get(models.Student, blocked_id).blocked_until = datetime.now() + timedelta(days=7)
            db.session.commit()
        response = blocked_client.post("/api/reserve", json=payload(seat_number=3))
        record("already_logged_in_blocked_student_reserves", status=response.status_code,
               body=response.get_json(silent=True))

        first, _, _ = student_client()
        second, _, _ = student_client()
        first_response = first.post("/api/reserve", json=payload(seat_number=4))
        conflict_response = second.post("/api/reserve", json=payload(seat_number=4))
        daily_response = first.post("/api/reserve", json=payload(seat_number=5))
        record("sequential_overlap_is_rejected", first=first_response.get_json(),
               second=conflict_response.get_json())
        record("second_daily_booking_is_rejected", body=daily_response.get_json())

        registration = app.test_client()
        response = registration.post("/register", data={"student_number": "bad",
                                     "name": "", "password": "x"})
        with app.app_context():
            saved = models.Student.query.filter_by(student_number="bad").first()
            record("invalid_registration_accepted", status=response.status_code,
                   saved=saved is not None, empty_name=saved.name == "" if saved else None,
                   short_pin_stored_plain=saved.pin_plain == "x" if saved else None)

        response = registration.post("/register", data={"student_number": "999999998",
                                     "name": "AUDIT NEW", "password": "654321"})
        login_response = registration.post("/login", data={"student_number": "999999998",
                                           "password": "654321"})
        with app.app_context():
            saved = models.Student.query.filter_by(student_number="999999998").first()
            record("registration_requires_approval", register_status=response.status_code,
                   is_approved=saved.is_approved, login_status=login_response.status_code,
                   pending_message="가입 승인을 기다리고" in login_response.get_data(as_text=True))
            db.session.remove()
            db.engine.dispose()
        sys.path.remove(str(copied))

    print(json.dumps({
        "scope": "Offline copy; synthetic data; no deployed service requests",
        "python": sys.version.split()[0],
        "packages": {name: importlib.metadata.version(name) for name in
                     ("Flask", "Flask-SQLAlchemy", "Flask-Login", "Werkzeug", "SQLAlchemy")},
        "checked_at": datetime.now().astimezone().isoformat(),
        "results": results,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
