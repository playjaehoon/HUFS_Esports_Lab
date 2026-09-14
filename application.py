"""Application factory used by WSGI, CLI and isolated tests."""
from datetime import timedelta
import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from flask_login import LoginManager, current_user
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFError, CSRFProtect
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError, OperationalError
from werkzeug.exceptions import HTTPException

from models import Admin, Student, db
from booking import RuleError, clock


def create_app(test_config=None):
    load_dotenv(Path(__file__).with_name('.env'))
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get('SECRET_KEY'),
        SQLALCHEMY_DATABASE_URI=os.environ.get('DATABASE_URL', 'sqlite:///esportslab.db'),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={'connect_args': {'timeout': 15}},
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=os.environ.get('APP_ENV', 'production') != 'development',
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        MAX_CONTENT_LENGTH=32 * 1024,
        AUTH_RATE_LIMIT_ENABLED=True,
    )
    if test_config:
        app.config.update(test_config)
    app.jinja_env.filters['clock'] = clock
    if not app.secret_key or len(app.secret_key) < 32:
        raise RuntimeError('SECRET_KEY에 새로 생성한 32자 이상의 무작위 키를 설정하세요.')
    if not app.config['SQLALCHEMY_DATABASE_URI'].startswith('sqlite:'):
        raise RuntimeError('현재 트랜잭션 구현은 SQLite 전용입니다. 다른 DB는 별도 검증이 필요합니다.')
    db.init_app(app)
    with app.app_context():
        @event.listens_for(db.engine, 'connect')
        def sqlite_connection(connection, _):
            cursor = connection.cursor()
            cursor.execute('PRAGMA foreign_keys=ON')
            cursor.execute('PRAGMA secure_delete=ON')
            cursor.close()
    Migrate(app, db, render_as_batch=True)
    CSRFProtect(app)
    login = LoginManager(app)

    @login.user_loader
    def load_user(value):
        try:
            role, identifier, version = value.split('_')
            model = {'admin': Admin, 'student': Student}.get(role)
            if model is None:
                return None
            user = db.session.get(model, int(identifier))
            return user if user and user.is_active and user.session_version == int(version) else None
        except (ValueError, TypeError):
            return None

    @login.unauthorized_handler
    def unauthorized():
        if request.path.startswith('/api/'):
            return jsonify(success=False, message='로그인이 필요합니다.'), 401
        return redirect(url_for('student_login'))

    @app.before_request
    def password_upgrade():
        if current_user.is_authenticated and isinstance(current_user._get_current_object(), Student):
            if (current_user.must_change_password and not session.get('password_change_skipped') and
                    request.endpoint not in {
                    'index', 'account', 'change_password', 'skip_password_change', 'logout', 'static'}):
                if request.path.startswith('/api/'):
                    raise RuleError('내 정보에서 비밀번호를 먼저 변경해 주세요.', 403)
                return redirect(url_for('account'))

    @app.after_request
    def security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'same-origin'
        if request.endpoint != 'static':
            response.headers['Cache-Control'] = 'no-store'
        return response

    def error(message, status):
        if request.path.startswith('/api/'):
            return jsonify(success=False, message=message), status
        return render_template('error.html', message=message), status

    @app.errorhandler(RuleError)
    def rule_error(exc):
        db.session.rollback()
        return error(str(exc), exc.status)

    @app.errorhandler(CSRFError)
    def csrf_error(_):
        return error('화면의 유효 시간이 지났습니다. 새로고침 후 다시 시도해 주세요.', 400)

    @app.errorhandler(HTTPException)
    def http_error(exc):
        messages = {400: '입력 내용을 확인해 주세요.', 403: '이 작업을 수행할 권한이 없습니다.',
                    404: '요청한 정보를 찾을 수 없습니다.', 405: '허용되지 않는 요청입니다.',
                    413: '입력 내용이 너무 깁니다.', 429: '요청이 많습니다. 15분 후 다시 시도해 주세요.'}
        response, status = error(messages.get(exc.code, '요청을 처리할 수 없습니다.'), exc.code)
        if status == 429:
            response = app.make_response((response, status))
            response.headers['Retry-After'] = '900'
            return response
        return response, status

    @app.errorhandler(IntegrityError)
    def integrity_error(_):
        db.session.rollback()
        return error('이미 등록되었거나 다른 요청이 먼저 처리했습니다. 새로고침 후 확인해 주세요.', 409)

    @app.errorhandler(OperationalError)
    def database_error(_):
        db.session.rollback()
        app.logger.error('Database operation unavailable; check migration and lock status.')
        return error('서비스 점검 중입니다. 잠시 후 다시 시도해 주세요.', 503)

    from routes import register_routes
    from commands import register_commands
    register_routes(app)
    register_commands(app)
    return app
