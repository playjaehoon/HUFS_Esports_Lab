"""New databases only. Existing legacy databases require import-legacy."""
from flask_migrate import upgrade
from application import create_app

if __name__ == '__main__':
    with create_app().app_context():
        upgrade()
    print('Schema upgraded. Create your own admin with: flask --app app admin-account')
