import os
from flask import request, jsonify
from werkzeug.utils import secure_filename
import re
import time

# --- CONFIGURATION SÉCURISÉE (VARIABLES D'ENVIRONNEMENT) ---

# L'adresse IP de votre Gateway (par défaut 127.0.0.1 pour les tests locaux)
GATEWAY_IP = os.environ.get("GATEWAY_IP") 

# La clé API secrète que le Gateway doit envoyer
SECRET_API_KEY = os.environ.get("TAKO_API_KEY")

# --- PARAMÈTRES WAF & UPLOADS ---
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
MAX_FILE_SIZE = 5 * 1024 * 1024 

# --- GESTION DU RATE LIMITING & BANNISSEMENT ---
ip_requests = {}
ip_bans = {} # Dictionnaire pour stocker l'état des bannissements

RATE_LIMIT = 50  # requêtes max
RATE_LIMIT_WINDOW = 60  # secondes

# Paliers de bannissement en secondes : 5m, 10m, 20m, 30m, 1h
BAN_STAGES = [300, 600, 1200, 1800, 3600]

# Regex basique pour détecter les tentatives d'injection SQL courantes
SQLI_PATTERN = re.compile(r"(?i)(UNION.*SELECT|DROP\s+TABLE|INSERT\s+INTO|UPDATE\s+.*SET|DELETE\s+FROM|--|;\s*--|OR\s+1\s*=\s*1|AND\s+1\s*=\s*1)")


def register_infraction(ip):
    """
    Applique une pénalité progressive à une IP.
    Monte de niveau à chaque infraction jusqu'au ban définitif.
    """
    if ip not in ip_bans:
        # Première infraction : Niveau 0 (5 minutes)
        ip_bans[ip] = {'level': 0, 'ban_until': time.time() + BAN_STAGES[0], 'permanent': False}
    elif not ip_bans[ip]['permanent']:
        # Infraction suivante : On monte d'un niveau
        next_level = ip_bans[ip]['level'] + 1
        
        if next_level >= len(BAN_STAGES) - 1:
            # Atteint le palier de 1h -> Bannissement définitif
            ip_bans[ip]['level'] = next_level
            ip_bans[ip]['permanent'] = True
            ip_bans[ip]['ban_until'] = float('inf') # Temps infini
        else:
            # Application du nouveau palier de temps
            ip_bans[ip]['level'] = next_level
            ip_bans[ip]['ban_until'] = time.time() + BAN_STAGES[next_level]


def init_security(app):
    """
    Initialise toutes les protections sur l'application Flask
    """
    
    @app.before_request
    def filter_requests():
        client_ip = request.remote_addr
        
        # 1. VÉRIFICATION DU BANNISSEMENT (À faire en tout premier)
        if client_ip in ip_bans:
            ban_info = ip_bans[client_ip]
            if ban_info['permanent']:
                return jsonify({"error": "Votre IP a été bannie définitivement pour comportement abusif."}), 403
            
            if time.time() < ban_info['ban_until']:
                remaining_time = int((ban_info['ban_until'] - time.time()) // 60)
                return jsonify({"error": f"IP temporairement bloquée. Réessayez dans {remaining_time} minutes."}), 429

        # 2. Vérification de la clé X-API-KEY (Sécurité Serveur-à-Serveur)
        api_key = request.headers.get("X-API-Key")
        if not api_key or api_key != SECRET_API_KEY:
            # Optionnel : Vous pouvez aussi enregistrer une infraction ici si on tente de deviner la clé
            # register_infraction(client_ip) 
            return jsonify({"error": "Accès refusé. Clé API invalide ou manquante."}), 401

        # 3. Protection DDoS / Restriction par IP Gateway (Détecte le Brute-Force)
        if client_ip != GATEWAY_IP:
            current_time = time.time()
            if client_ip not in ip_requests:
                ip_requests[client_ip] = []
            
            # Nettoyer les vieilles requêtes
            ip_requests[client_ip] = [t for t in ip_requests[client_ip] if current_time - t < RATE_LIMIT_WINDOW]
            
            if len(ip_requests[client_ip]) >= RATE_LIMIT:
                register_infraction(client_ip)
                ban_level = ip_bans[client_ip]['level']
                ban_minutes = BAN_STAGES[ban_level] // 60
                return jsonify({"error": f"Brute-force détecté. IP bloquée pour {ban_minutes} minutes."}), 429
            
            ip_requests[client_ip].append(current_time)

        # 4. Protection contre les Injections SQL (WAF basique)
        def check_sqli(value):
            if SQLI_PATTERN.search(str(value)):
                register_infraction(client_ip)
                return True
            return False

        # Vérification des paramètres d'URL
        for key, value in request.args.items():
            if check_sqli(value):
                return jsonify({"error": "Requête malveillante détectée. IP pénalisée."}), 400
                
        # Vérification des données JSON entrantes
        if request.is_json:
            try:
                data = str(request.get_json())
                if check_sqli(data):
                    return jsonify({"error": "Requête malveillante détectée. IP pénalisée."}), 400
            except:
                pass
                
        # Vérification des données des formulaires
        for key, value in request.form.items():
            if check_sqli(value):
                return jsonify({"error": "Requête malveillante détectée. IP pénalisée."}), 400


def is_safe_image(file):
    """
    Vérifie qu'un fichier entrant est bien une image sécurisée :
    - Vérifie la taille maximale (5 Mo)
    - Bloque les doubles extensions (ex: .php.jpg)
    - Restreint strictement aux formats png, jpg, jpeg
    """
    if not file or not file.filename:
        return False, "Aucun fichier fourni."

    # Vérification de la taille
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0) 
    
    if file_size > MAX_FILE_SIZE:
        return False, "Fichier trop volumineux."

    # Sécurisation du nom
    filename = secure_filename(file.filename)
    
    if filename.count('.') > 1:
        return False, "Les doubles extensions sont interdites."
        
    if '.' not in filename:
        return False, "Le fichier n'a pas d'extension."
        
    ext = filename.rsplit('.', 1)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return False, "Extension non autorisée"
    
    return True, filename