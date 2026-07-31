from flask import Blueprint, jsonify, request
from src.services.auth_service import register_user
from securite.securite import is_safe_image

# Blueprint dédié uniquement à l'inscription
register_bp = Blueprint("register", __name__)


@register_bp.route("/register", methods=["POST"])
def register():
    # 1. Champs texte obligatoires
    tel = request.form.get("tel")
    password = request.form.get("password")
    nom = request.form.get("nom")
    prenom = request.form.get("prenom")
    sexe = request.form.get("sexe")
    adresse = request.form.get("adresse")
    matricule = request.form.get("matricule")

    # Champs optionnels
    email = request.form.get("email")
    postnom = request.form.get("postnom")

    # Vérification des champs texte
    if not all([tel, password, nom, prenom, sexe, adresse, matricule]):
        return jsonify({
            "message": "Les champs tel, password, nom, prenom, sexe, adresse et matricule sont obligatoires"
        }), 400

    # 2. Récupération et vérification OBLIGATOIRE des fichiers
    profil_file = request.files.get("profil")
    permis_file = request.files.get("permis")

    if not profil_file or not profil_file.filename:
        return jsonify({"message": "La photo de profil est obligatoire"}), 400

    if not permis_file or not permis_file.filename:
        return jsonify({"message": "La photo du permis de conduire est obligatoire"}), 400

    # 3. Validation de sécurité des images (Taille, Extension, etc.)
    is_safe_p, result_p = is_safe_image(profil_file)
    if not is_safe_p:
        return jsonify({"message": f"Erreur image profil : {result_p}"}), 400

    is_safe_m, result_m = is_safe_image(permis_file)
    if not is_safe_m:
        return jsonify({"message": f"Erreur image permis : {result_m}"}), 400

    # 4. Appel direct du service (On passe directement les fichiers sans les enregistrer sur le disque !)
    user_id, error = register_user(
        tel=tel,
        password=password,
        nom=nom,
        prenom=prenom,
        sexe=sexe,
        adresse=adresse,
        matricule=matricule,
        profil_file=profil_file,  # <-- Transmis directement à Cloudinary via votre service
        permis_file=permis_file,  # <-- Transmis directement à Cloudinary via votre service
        email=email,
        postnom=postnom
    )

    if error:
        return jsonify({"message": error}), 400

    return jsonify({"message": "Utilisateur créé avec succès", "id_user": user_id}), 201