from flask import Flask
from src.models.user_model import db
from src.routes.login import login_bp
from src.routes.register import register_bp
from src.routes.forgot_password import forgot_password_bp

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "mysql+mysqlconnector://user:password@db/auth_db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)

app.register_blueprint(login_bp)
app.register_blueprint(register_bp)
app.register_blueprint(forgot_password_bp)

if __name__ == "__main__":
    with app.app_context():
        db.create_all() # Crée les tables si elles n'existent pas
    app.run(host="0.0.0.0", port=5001)
