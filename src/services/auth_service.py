import os
import logging
import time
import uuid  # <-- Importation pour générer l'identifiant unique
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import cloudinary
import cloudinary.uploader
from src.data import fetch_one, Database 

# ==========================================
# 1. CONFIGURATION ET VARIABLES GLOBALES
# ==========================================

# Configuration du logger serveur pour la traçabilité de la sécurité
logger = logging.getLogger("auth_service")

# Configuration de Cloudinary via les variables d'environnement
cloudinary.config(
    cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME"),
    api_key=os.environ.get("CLOUDINARY_API_KEY"),
    api_secret=os.environ.get("CLOUDINARY_API_SECRET"),
    secure=True
)

# Messages génériques renvoyés au client HTTP
GENERIC_REGISTRATION_ERROR = "Impossible de procéder à l'inscription avec ces informations. Veuillez vérifier vos données."
GENERIC_LOGIN_ERROR = "Identifiants ou mot de passe incorrects."

# Configuration Anti Brute-Force
MAX_FAILED_ATTEMPTS = 5       
LOCKOUT_TIME_SECONDS = 300    

failed_logins = {}


# ==========================================
# 2. FONCTIONS UTILITAIRES (SÉCURITÉ & CLOUD)
# ==========================================

def _record_failed_attempt(identifier):
    """
    Incrémente le compteur d'échecs pour un identifiant donné.
    Verrouille le compte temporairement si la limite maximale est atteinte.
    """
    current_time = time.time()
    
    if identifier not in failed_logins:
        failed_logins[identifier] = {'count': 1, 'lock_until': 0}
    else:
        failed_logins[identifier]['count'] += 1

    if failed_logins[identifier]['count'] >= MAX_FAILED_ATTEMPTS:
        failed_logins[identifier]['lock_until'] = current_time + LOCKOUT_TIME_SECONDS
        logger.warning(f"[SECURITY - ACCOUNT LOCKED] L'identifiant {identifier} a été bloqué temporairement.")


def upload_to_cloudinary(file_obj, folder_name, file_name):
    """
    Upload un fichier image vers Cloudinary dans un dossier précis et avec un nom précis.
    """
    try:
        if not file_obj:
            return None, "Aucun fichier d'image fourni."

        if hasattr(file_obj, 'seek'):
            file_obj.seek(0)

        # Envoi à Cloudinary (folder = dossier, public_id = nom du fichier)
        upload_result = cloudinary.uploader.upload(
            file_obj,
            folder=folder_name,
            public_id=file_name,
            resource_type="image"
        )

        secure_url = upload_result.get("secure_url")
        if not secure_url:
            return None, "Échec de récupération de l'URL sur Cloudinary."

        return secure_url, None

    except Exception as e:
        logger.error(f"[CLOUDINARY ERROR] Échec de l'upload vers {folder_name} : {str(e)}", exc_info=True)
        return None, "Erreur lors du transfert de l'image vers le serveur Cloud."


# ==========================================
# 3. SERVICES D'AUTHENTIFICATION
# ==========================================

def register_user(tel, password, nom, prenom, sexe, adresse, matricule, profil_file, permis_file, email=None, postnom=None):
    """
    Crée un nouvel utilisateur : génère un UUID, uploade les images sur Cloudinary,
    puis enregistre les informations en base de données.
    """
    # A. Vérification obligatoire des fichiers images (Profil et Permis)
    if not profil_file:
        logger.warning("[REGISTRATION REJECTED] Tentative d'inscription sans photo de profil.")
        return None, "La photo de profil est obligatoire"

    if not permis_file:
        logger.warning("[REGISTRATION REJECTED] Tentative d'inscription sans photo de permis.")
        return None, "La photo du permis de conduire est obligatoire"

    # B. Vérification des doublons en base (Téléphone, Email, Matricule)
    if fetch_one("SELECT id_user FROM user WHERE tel = %s", (tel,)):
        logger.warning(f"[SECURITY ALERT - DUPLICATE TEL] Tentative d'inscription avec un téléphone déjà existant : {tel}")
        return None, GENERIC_REGISTRATION_ERROR

    if email and fetch_one("SELECT id_user FROM user WHERE email = %s", (email,)):
        logger.warning(f"[SECURITY ALERT - DUPLICATE EMAIL] Tentative d'inscription avec un email déjà existant : {email}")
        return None, GENERIC_REGISTRATION_ERROR
        
    if fetch_one("SELECT id_user FROM user_info WHERE matricule = %s", (matricule,)):
        logger.warning(f"[SECURITY ALERT - DUPLICATE MATRICULE] Tentative d'inscription avec un matricule déjà existant : {matricule}")
        return None, GENERIC_REGISTRATION_ERROR

    # C. Préparation des variables Cloudinary (Dossier et noms de fichiers)
    user_uuid = str(uuid.uuid4())[:8]  # On prend les 8 premiers caractères de l'UUID pour garder des URLs propres
    nom_propre = nom.replace(" ", "_").strip()  # Enlève les espaces pour éviter les erreurs d'URL
    
    dossier_utilisateur = f"tako/chauffeurs/{user_uuid}_{nom_propre}"
    nom_fichier_profil = f"{user_uuid}_{nom_propre}_profil"
    nom_fichier_permis = f"{user_uuid}_{nom_propre}_permis"

    # D. Téléversement des images sur Cloudinary (Avant l'insertion en base !)
    profil_url, err_profil = upload_to_cloudinary(
        profil_file, 
        folder_name=dossier_utilisateur, 
        file_name=nom_fichier_profil
    )
    if err_profil:
        return None, f"Photo de profil : {err_profil}"

    permis_url, err_permis = upload_to_cloudinary(
        permis_file, 
        folder_name=dossier_utilisateur, 
        file_name=nom_fichier_permis
    )
    if err_permis:
        return None, f"Photo du permis : {err_permis}"

    # E. Préparation des données sécurisées pour MySQL
    hashed_password = generate_password_hash(password)
    id_tpcompte = 1  # Rôle par défaut (ex: 1 pour Chauffeur)
    date_creation = datetime.now()

    try:
        # F. Insertion en base de données (Transaction via 'with Database()')
        with Database() as cursor:
            # 1. Insertion de l'utilisateur principal
            query_user = """
                INSERT INTO user (email, tel, password, id_tpcompte, date_creation)
                VALUES (%s, %s, %s, %s, %s)
            """
            cursor.execute(query_user, (email, tel, hashed_password, id_tpcompte, date_creation))
            new_user_id = cursor.lastrowid

            # 2. Insertion des informations du profil (stockage des URLs Cloudinary)
            query_info = """
                INSERT INTO user_info (nom, postnom, prenom, sexe, adresse, matricule, profil, permis, id_user)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(query_info, (nom, postnom, prenom, sexe, adresse, matricule, profil_url, permis_url, new_user_id))

        logger.info(f"[REGISTRATION SUCCESS] Nouvel utilisateur créé. ID : {new_user_id} | Dossier Cloud : {dossier_utilisateur}")
        return new_user_id, None

    except Exception as e:
        logger.error(f"[SYSTEM ERROR] Échec d'insertion en base de données : {str(e)}", exc_info=True)
        return None, "Une erreur système est survenue lors de la création du compte."

    
def login_user(identifier, password):
    """
    Vérifie les accès d'un utilisateur avec protection anti force-brute.
    L'identifiant peut être le téléphone ou l'email.
    """
    # A. Vérification de base des entrées
    if not identifier or not password:
        logger.warning("[LOGIN ATTEMPT FAILED] Tentative de connexion avec champs vides.")
        return None, GENERIC_LOGIN_ERROR

    current_time = time.time()

    # B. Vérification Anti Brute-Force (Le compte est-il verrouillé ?)
    if identifier in failed_logins:
        lock_until = failed_logins[identifier].get('lock_until', 0)
        
        # Rejet immédiat si le compte est encore sous verrouillage
        if current_time < lock_until:
            remaining_time = int((lock_until - current_time) / 60) + 1
            logger.warning(f"[SECURITY - BRUTE FORCE] Connexion bloquée pour {identifier}. Temps restant: {remaining_time}m")
            return None, f"Trop de tentatives échouées. Veuillez réessayer dans {remaining_time} minute(s)."
        
        # Réinitialisation si le temps de verrouillage est expiré
        elif current_time > lock_until and failed_logins[identifier]['count'] >= MAX_FAILED_ATTEMPTS:
            failed_logins[identifier] = {'count': 0, 'lock_until': 0}

    # C. Recherche de l'utilisateur en base de données
    query = """
        SELECT u.id_user, u.tel, u.email, u.password, u.id_tpcompte,
               ui.nom, ui.prenom, ui.profil
        FROM user u
        LEFT JOIN user_info ui ON u.id_user = ui.id_user
        WHERE u.tel = %s OR u.email = %s
    """
    
    try:
        user = fetch_one(query, (identifier, identifier))

        # D. Vérification de l'existence de l'utilisateur
        if not user:
            logger.warning(f"[LOGIN FAILED - UNKNOWN USER] Identifiant introuvable : {identifier}")
            _record_failed_attempt(identifier)
            return None, GENERIC_LOGIN_ERROR

        # E. Vérification du mot de passe
        if check_password_hash(user['password'], password):
            # --- SUCCÈS ---
            logger.info(f"[LOGIN SUCCESS] Utilisateur connecté. ID : {user['id_user']}")
            
            # Effacement des tentatives échouées après un succès
            if identifier in failed_logins:
                del failed_logins[identifier]
            
            # Suppression du mot de passe en clair pour la sécurité du payload renvoyé
            del user['password']
            return user, None
        else:
            # --- ÉCHEC (Mauvais mot de passe) ---
            logger.warning(f"[LOGIN FAILED - WRONG PASSWORD] Mot de passe incorrect pour ID : {user['id_user']}")
            _record_failed_attempt(identifier)
            return None, GENERIC_LOGIN_ERROR

    except Exception as e:
        logger.error(f"[SYSTEM ERROR] Erreur lors de la connexion de '{identifier}': {str(e)}", exc_info=True)
        return None, "Une erreur système est survenue. Veuillez réessayer plus tard."