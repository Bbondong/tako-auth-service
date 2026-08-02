from flask import Blueprint, jsonify, request
from src.services.auth_service import login_user

login_bp = Blueprint("login", __name__)

@login_bp.route("/login", methods=["POST"])
def login():
    # 1. Accepter à la fois le format JSON et le format Form-Data (très important avec le Gateway)
    if request.is_json:
        data = request.get_json(silent=True) or {}
    else:
        data = request.form.to_dict()

    # 2. Récupérer l'identifiant (que le front envoie "username", "email", "tel" ou "identifier")
    identifier = data.get("identifier") or data.get("username") or data.get("email") or data.get("tel")
    password = data.get("password")

    # 3. Vérifier que les champs ne sont pas vides
    if not identifier or not password:
        return jsonify({"message": "L'identifiant et le mot de passe sont obligatoires."}), 400

    # 4. Appeler le service d'authentification
    user, error = login_user(identifier, password)
    
    if error:
        return jsonify({"message": error}), 401


    return jsonify({
        "message": "Login successful", 
        "user_id": user['id_user'],
        "user": user  # On renvoie les infos de l'utilisateur pour l'application mobile
    }), 200