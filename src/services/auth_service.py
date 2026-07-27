from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from src.data import fetch_one, Database 

def register_user(tel, password, nom, prenom, sexe, adresse, profil_path, permis_path, email=None, postnom=None):
    """
    Vérifie les champs obligatoires, les doublons, puis crée l'utilisateur et son profil.
    """
    # 0. Vérification obligatoire des images (Profil et Permis)
    if not profil_path or not str(profil_path).strip():
        return None, "La photo de profil est obligatoire"

    if not permis_path or not str(permis_path).strip():
        return None, "La photo du permis de conduire est obligatoire"

    # 1. Vérification si le téléphone existe déjà
    if fetch_one("SELECT id_user FROM user WHERE tel = %s", (tel,)):
        return None, "Un utilisateur avec ce numéro de téléphone existe déjà"

    # Vérification de l'email s'il est fourni
    if email and fetch_one("SELECT id_user FROM user WHERE email = %s", (email,)):
        return None, "Un utilisateur avec cet email existe déjà"

    # 2. Hachage du mot de passe
    hashed_password = generate_password_hash(password)
    id_tpcompte = 1
    date_creation = datetime.now()

    try:
        # 3. Insertion en base de données
        with Database() as cursor:
            # Création de l'utilisateur principal
            query_user = """
                INSERT INTO user (email, tel, password, id_tpcompte, date_creation)
                VALUES (%s, %s, %s, %s, %s)
            """
            cursor.execute(query_user, (email, tel, hashed_password, id_tpcompte, date_creation))
            
            new_user_id = cursor.lastrowid

            # Création du profil utilisateur avec les chemins des images validés
            query_info = """
                INSERT INTO user_info (nom, postnom, prenom, sexe, adresse, profil, permis, id_user)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(query_info, (nom, postnom, prenom, sexe, adresse, profil_path, permis_path, new_user_id))

        return new_user_id, None

    except Exception as e:
        return None, f"Erreur système lors de la création du compte : {str(e)}"

def login_user(identifier, password):
    """
    Vérifie les accès de l'utilisateur. 'identifier' peut être le téléphone ou l'email.
    """
    # 1. On cherche l'utilisateur par téléphone ou email (remplace filter_by)
    # On fait un JOIN pour récupérer aussi son nom/prénom et son profil dès la connexion
    query = """
        SELECT u.id_user, u.tel, u.email, u.password, u.id_tpcompte,
               ui.nom, ui.prenom, ui.profil
        FROM user u
        LEFT JOIN user_info ui ON u.id_user = ui.id_user
        WHERE u.tel = %s OR u.email = %s
    """
    user = fetch_one(query, (identifier, identifier))

    # 2. Vérification de l'existence et du mot de passe (remplace user.check_password)
    if user and check_password_hash(user['password'], password):
        # Pour des raisons de sécurité, on retire le mot de passe avant de renvoyer l'objet
        del user['password']
        return user, None
        
    return None, "Numéro de téléphone/email ou mot de passe incorrect"