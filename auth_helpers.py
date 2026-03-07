import flask_login

# Make Admin and Student share the same namespace for flask-login, or differentiate them
# For simplicity, since login_manager needs to load users by ID, we'll prefix IDs to separate Admin and Student
@login_manager.user_loader
def load_user(user_id):
    if user_id.startswith('admin_'):
        return Admin.query.get(int(user_id.split('_')[1]))
    elif user_id.startswith('student_'):
        return Student.query.get(int(user_id.split('_')[1]))
    return None
