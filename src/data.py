import os
import pymysql
import pymysql.cursors
from dotenv import load_dotenv

# Charger les variables d'environnement du fichier .env
load_dotenv()

def get_connection():
    """
    Établit et retourne une connexion directe à la base de données MySQL.
    """
    host = os.getenv('DB_HOST', 'localhost')
    user = os.getenv('DB_USER', 'root')
    password = os.getenv('DB_PASSWORD', '')
    database = os.getenv('DB_NAME', '')
    port = int(os.getenv('DB_PORT', 3306))

    if not database:
        raise ValueError("La variable DB_NAME doit être définie dans le fichier .env")

    return pymysql.connect(
        host=host,
        user=user,
        password=password,
        database=database,
        port=port,
        cursorclass=pymysql.cursors.DictCursor,  # Retourne les résultats sous forme de dictionnaire {'colonne': valeur}
        autocommit=False
    )


def init_db(app=None):
    """
    Teste la connexion à la base de données MySQL.
    Affiche un message de succès ou lève une exception en cas d'échec.
    """
    try:
        connection = get_connection()
        with connection.cursor() as cursor:
            cursor.execute("SELECT VERSION() AS version;")
            result = cursor.fetchone()
            print(f"✅ Connexion MySQL réussie ! Version du serveur : {result['version']}")
        connection.close()
    except Exception as e:
        print(f"❌ Échec de la connexion à MySQL : {e}")
        raise e


class Database:
    """
    Gestionnaire de contexte pour gérer automatiquement l'ouverture,
    le commit, le rollback et la fermeture des connexions MySQL.
    """
    def __enter__(self):
        self.conn = get_connection()
        self.cursor = self.conn.cursor()
        return self.cursor

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            # En cas d'erreur, annuler les changements
            self.conn.rollback()
        else:
            # Sinon, valider la transaction
            self.conn.commit()
        
        # Fermer le curseur et la connexion
        self.cursor.close()
        self.conn.close()


# --- FONCTIONS UTILITAIRES POUR EXÉCUTER TES REQUÊTES ---

def execute_query(query: str, params: tuple = ()):
    """
    Exécute une requête de modification (INSERT, UPDATE, DELETE).
    """
    with Database() as cursor:
        cursor.execute(query, params)
        return cursor.lastrowid  # Retourne l'ID généré si c'est un INSERT


def fetch_all(query: str, params: tuple = ()):
    """
    Exécute une requête SELECT et retourne TOUS les résultats (liste de dictionnaires).
    """
    with Database() as cursor:
        cursor.execute(query, params)
        return cursor.fetchall()


def fetch_one(query: str, params: tuple = ()):
    """
    Exécute une requête SELECT et retourne UN seul résultat (dictionnaire).
    """
    with Database() as cursor:
        cursor.execute(query, params)
        return cursor.fetchone()


