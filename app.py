from flask import Flask
# from src.routes.login import login_bp
from src.routes.register import register_bp
# from src.routes.forgot_password import forgot_password_bp

app = Flask(__name__)

# app.register_blueprint(login_bp)
app.register_blueprint(register_bp)
# app.register_blueprint(forgot_password_bp)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)