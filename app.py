from flask import Flask
from src.models.user_model import db
from src.routes.auth_routes import auth_bp

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "mysql+mysqlconnector://user:password@db/auth_db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)

app.register_blueprint(auth_bp)

if __name__ == "__main__":
    with app.app_context():
        db.create_all() # Crée les tables si elles n'existent pas
    app.run(host="0.0.0.0", port=5001)
