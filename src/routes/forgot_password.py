from flask import Blueprint, jsonify, request

forgot_password_bp = Blueprint("forgot_password", __name__)

@forgot_password_bp.route("/forgot_password", methods=["POST"])
def forgot_password():
    data = request.get_json()
    email = data.get("email")

    if not email:
        return jsonify({"message": "Missing email"}), 400

    # Ici, vous implémenteriez la logique pour envoyer un e-mail de réinitialisation de mot de passe.
    # Cela impliquerait probablement de générer un token de réinitialisation, de le stocker en base de données
    # et d'envoyer un lien contenant ce token à l'adresse e-mail de l'utilisateur.

    return jsonify({"message": "If an account with that email exists, a password reset link has been sent."}), 200
