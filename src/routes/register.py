import os
import time
from flask import Blueprint, jsonify, request
from werkzeug.utils import secure_filename
from src.services.auth_service import register_user

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
    # 1. Récupération des données texte depuis request.form (pour le multipart/form-data)
    tel = request.form.get("tel")
    password = request.form.get("password")
    nom = request.form.get("nom")
    prenom = request.form.get("prenom")
    sexe = request.form.get("sexe")
    adresse = request.form.get("adresse")
    
    # Champs optionnels
    email = request.form.get("email")
    postnom = request.form.get("postnom")

    # Vérification des champs obligatoires
    if not all([tel, password, nom, prenom, sexe, adresse]):
        return jsonify({"message": "Les champs tel, password, nom, prenom, sexe et adresse sont obligatoires"}), 400

    # 2. Récupération et sauvegarde des fichiers
    profil_file = request.files.get("profil")
    permis_file = request.files.get("permis")

    # Valeurs par défaut si aucun fichier n'est envoyé
    profil_path = "default_profil.png"
    permis_path = "aucun_permis.png"

    # Sauvegarde de la photo de profil
    if profil_file and profil_file.filename:
        filename = f"{int(time.time())}_{secure_filename(profil_file.filename)}"
        filepath = os.path.join(PROFIL_FOLDER, filename)
        profil_file.save(filepath)
        profil_path = filepath  # Chemin à sauvegarder en base

    # Sauvegarde de la photo du permis
    if permis_file and permis_file.filename:
        filename = f"{int(time.time())}_{secure_filename(permis_file.filename)}"
        filepath = os.path.join(PERMIS_FOLDER, filename)
        permis_file.save(filepath)
        permis_path = filepath

    # 3. Appel du service
    user_id, error = register_user(
        tel=tel, password=password, nom=nom, prenom=prenom,
        sexe=sexe, adresse=adresse, profil_path=profil_path, 
        permis_path=permis_path, email=email, postnom=postnom
    )

    if error:
        return jsonify({"message": error}), 409

    return jsonify({"message": "Utilisateur créé avec succès", "id_user": user_id}), 201