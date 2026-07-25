from flask import Blueprint, jsonify, request
from src.services.auth_service import register_user, login_user
from src.models.user_model import db

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/", methods=["GET"])
def health_check():
    return jsonify({"status": "Auth service is up and running!"}), 200

@auth_bp.route("/register", methods=["POST"])
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

@auth_bp.route("/login", methods=["POST"])
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
