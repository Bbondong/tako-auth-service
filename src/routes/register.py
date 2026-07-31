import os
import time
from flask import Blueprint, jsonify, request
from werkzeug.utils import secure_filename
from src.services.auth_service import register_user
from securite.securite import is_safe_image

# Blueprint dédié uniquement à l'inscription
register_bp = Blueprint("register", __name__)

# --- CONFIGURATION DES DOSSIERS D'UPLOAD ---
BASE_DIR = os.path.abspath(os.path.dirname(__name__))
PROFIL_FOLDER = os.path.join(BASE_DIR, 'uploads', 'profils')
PERMIS_FOLDER = os.path.join(BASE_DIR, 'uploads', 'permis')

# Création automatique des dossiers s'ils n'existent pas
os.makedirs(PROFIL_FOLDER, exist_ok=True)
os.makedirs(PERMIS_FOLDER, exist_ok=True)


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

    # --- Traitement et sauvegarde de la photo de profil ---
    is_safe_p, result_p = is_safe_image(profil_file)
    if not is_safe_p:
        return jsonify({"message": f"Erreur image profil : {result_p}"}), 400

    filename_profil = f"{int(time.time())}_{result_p}"
    filepath_profil = os.path.join(PROFIL_FOLDER, filename_profil)
    profil_file.save(filepath_profil)
    profil_path = f"uploads/profils/{filename_profil}"

    # --- Traitement et sauvegarde de la photo du permis ---
    is_safe_m, result_m = is_safe_image(permis_file)
    if not is_safe_m:
        return jsonify({"message": f"Erreur image permis : {result_m}"}), 400

    filename_permis = f"{int(time.time())}_{result_m}"
    filepath_permis = os.path.join(PERMIS_FOLDER, filename_permis)
    permis_file.save(filepath_permis)
    permis_path = f"uploads/permis/{filename_permis}"

    # 3. Appel du service d'inscription
    user_id, error = register_user(
        tel=tel, password=password, nom=nom, prenom=prenom,
        sexe=sexe, adresse=adresse, matricule=matricule,
        profil_path=profil_path, permis_path=permis_path,
        email=email, postnom=postnom
    )

    if error:
        return jsonify({"message": error}), 409

    return jsonify({"message": "Utilisateur créé avec succès", "id_user": user_id}), 201