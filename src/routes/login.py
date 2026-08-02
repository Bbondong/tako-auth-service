from flask import Blueprint, request, jsonify
# Assure-toi que l'import correspond à l'arborescence de ton projet
from services.auth_service import login_user 

# Création du Blueprint pour la route de connexion
login_bp = Blueprint("login", __name__)

@login_bp.route("/login", methods=["POST"])
def login():
    """
    Route pour authentifier un utilisateur.
    Accepte à la fois le format JSON et FormData.
    """
    try:
        # 1. Récupération des données (supporte le JSON pur et le multipart/form-data)
        if request.is_json:
            data = request.get_json(silent=True) or {}
        else:
            data = request.form.to_dict()

        # 2. Extraction de l'identifiant (téléphone ou email) et du mot de passe
        # On vérifie plusieurs clés possibles selon ce que ton front-end envoie
        identifier = data.get("identifier") or data.get("tel") or data.get("email")
        password = data.get("password")

        # Vérification si les champs sont vides
        if not identifier or not password:
            return jsonify({"error": "L'identifiant et le mot de passe sont obligatoires."}), 400

        # 3. Appel au service d'authentification (celui que tu m'as envoyé tout à l'heure)
        user, error = login_user(identifier, password)

        # 4. Gestion de l'erreur (Mauvais mot de passe, brute-force, introuvable)
        if error:
            return jsonify({"error": error}), 401

        # 5. ✅ SUCCÈS - LA CORRECTION EST ICI : on utilise user['id_user']
        return jsonify({
            "message": "Login successful",
            "user_id": user['id_user'],
            "user": user  # On renvoie aussi les détails de l'utilisateur (sans le mot de passe) pour l'app mobile
        }), 200

    except Exception as e:
        return jsonify({
            "error": "Une erreur inattendue est survenue lors de la connexion.",
            "details": str(e)
        }), 500