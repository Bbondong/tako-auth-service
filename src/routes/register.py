from flask import Blueprint, jsonify, request
from src.services.auth_service import register_user

register_bp = Blueprint("register", __name__)

@register_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    username = data.get("username")
    email = data.get("email")
    password = data.get("password")

    if not all([username, email, password]):
        return jsonify({"message": "Missing username, email or password"}), 400

    user, error = register_user(username, email, password)
    if error:
        return jsonify({"message": error}), 409

    return jsonify({"message": "User registered successfully", "user_id": user.id}), 201
