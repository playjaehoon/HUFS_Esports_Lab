"""Role checks and database-backed authentication throttling."""
from datetime import timedelta, timezone
from functools import wraps
import hashlib
import hmac
from flask import abort, current_app, request
from flask_login import current_user, login_required
from sqlalchemy.dialects.sqlite import insert
from models import Admin, Student, LoginAttempt, db, utcnow


def role_required(model):
    def decorate(func):
        @wraps(func)
        @login_required
        def wrapped(*args, **kwargs):
            if not isinstance(current_user._get_current_object(), model):
                abort(403)
            return func(*args, **kwargs)
        return wrapped
    return decorate


admin_required = role_required(Admin)
student_required = role_required(Student)


def throttle(namespace, identifier, limit=10):
    """Count before password checking, shared across SQLite workers.

    Do not trust X-Forwarded-For without verified proxy configuration.
    Account limits remain effective behind shared proxy addresses.
    """
    if not current_app.config['AUTH_RATE_LIMIT_ENABLED']:
        return
    now = utcnow()
    bucket = int(now.replace(tzinfo=timezone.utc).timestamp()) // 900
    secret = current_app.secret_key.encode()
    blocked = False
    db.session.execute(db.delete(LoginAttempt).where(LoginAttempt.expires_at < now))
    for scope, value, ceiling in [('account', identifier, limit), ('network', request.remote_addr or '', 200)]:
        raw = f'{namespace}:{scope}:{value[:200]}:{bucket}'.encode()
        key = hmac.new(secret, raw, hashlib.sha256).hexdigest()
        statement = insert(LoginAttempt).values(key=key, count=1, expires_at=now + timedelta(minutes=30))
        db.session.execute(statement.on_conflict_do_update(index_elements=['key'], set_={'count': LoginAttempt.count + 1}))
        count = db.session.scalar(db.select(LoginAttempt.count).where(LoginAttempt.key == key))
        blocked |= count > ceiling
    db.session.commit()
    if blocked:
        abort(429)
