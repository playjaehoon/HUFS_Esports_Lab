from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class Admin(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

class Student(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_number = db.Column(db.String(9), unique=True, nullable=False) # 9-digit
    name = db.Column(db.String(50), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False) # PIN hash
    pin_plain = db.Column(db.String(10), nullable=True) # Optional plain view for admins
    blocked_until = db.Column(db.DateTime, nullable=True) # Block end date (if any)
    is_approved = db.Column(db.Boolean, default=False) # Admin approval status

class Reservation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(20), nullable=False)
    student_name = db.Column(db.String(50), nullable=False)
    date = db.Column(db.String(10), nullable=False) # Format: YYYY-MM-DD
    start_time = db.Column(db.Integer, nullable=False) # Format: 9 to 17
    end_time = db.Column(db.Integer, nullable=False)   # Format: 10 to 18 (max 3 hours duration)
    seat_number = db.Column(db.Integer, nullable=False) # 1 to 28
    status = db.Column(db.String(20), nullable=False, default='active') # 'active' or 'cancelled'
    is_attended = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class BlockedTime(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(10), nullable=False) # 'YYYY-MM-DD'
    start_time = db.Column(db.Integer, nullable=True) # e.g. 9
    end_time = db.Column(db.Integer, nullable=True)   # e.g. 12. If both Null, whole day is blocked.

class Setting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.String(255), nullable=False)
