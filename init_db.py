from models import db, Admin, Setting
from werkzeug.security import generate_password_hash
from app import app

def init_db():
    with app.app_context():
        db.create_all()
        
        # Check if admin exists
        admin = Admin.query.filter_by(username='admin').first()
        if not admin:
            # Create default admin: admin / admin123
            new_admin = Admin(
                username='admin',
                password_hash=generate_password_hash('admin123')
            )
            db.session.add(new_admin)
            
        # Set default settings
        res_open = Setting.query.filter_by(key='reservation_open').first()
        if not res_open:
            db.session.add(Setting(key='reservation_open', value='1'))
        
        max_hrs = Setting.query.filter_by(key='max_hours').first()
        if not max_hrs:
            db.session.add(Setting(key='max_hours', value='3'))
            
        notice = Setting.query.filter_by(key='notice').first()
        if not notice:
            db.session.add(Setting(key='notice', value='Welcome to Philips Evnia Esports Lab!'))
            
        db.session.commit()
        print("Database initialized successfully!")

if __name__ == '__main__':
    init_db()
