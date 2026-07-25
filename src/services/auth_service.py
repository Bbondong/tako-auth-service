from src.models.user_model import db, User

def register_user(username, email, password):
    if User.query.filter_by(username=username).first() or User.query.filter_by(email=email).first():
        return None, "User with this username or email already exists"

    new_user = User(username=username, email=email)
    new_user.set_password(password)
    db.session.add(new_user)
    db.session.commit()
    return new_user, None

def login_user(username, password):
    user = User.query.filter_by(username=username).first()
    if user and user.check_password(password):
        return user, None
    return None, "Invalid credentials"
