from flask import Blueprint, jsonify, request
from src.services.auth_service import login_user

login_bp = Blueprint("login", __name__)

@login_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")

    if not all([username, password]):
        return jsonify({"message": "Missing username or password"}), 400

    user, error = login_user(username, password)
    if error:
        return jsonify({"message": error}), 401

    return jsonify({"message": "Login successful", "user_id": user.id}), 200
