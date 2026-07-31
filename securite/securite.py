import os
import re
import time
from flask import request, jsonify
from werkzeug.utils import secure_filename

# --- PARAMÈTRES WAF & UPLOADS ---
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
MAX_FILE_SIZE = 5 * 1024 * 1024 

# --- GESTION DU RATE LIMITING & BANNISSEMENT ---
ip_requests = {}
ip_bans = {}

RATE_LIMIT = 50  # requêtes max
RATE_LIMIT_WINDOW = 60  # secondes

BAN_STAGES = [300, 600, 1200, 1800, 3600]

SQLI_PATTERN = re.compile(
    r"(?i)(UNION.*SELECT|DROP\s+TABLE|INSERT\s+INTO|UPDATE\s+.*SET|DELETE\s+FROM|--|;\s*--|OR\s+1\s*=\s*1|AND\s+1\s*=\s*1)"
)


def register_infraction(ip):
    """
    Applique une pénalité progressive à une IP.
    """
    if ip not in ip_bans:
        ip_bans[ip] = {'level': 0, 'ban_until': time.time() + BAN_STAGES[0], 'permanent': False}
    elif not ip_bans[ip]['permanent']:
        next_level = ip_bans[ip]['level'] + 1
        if next_level >= len(BAN_STAGES) - 1:
            ip_bans[ip]['level'] = next_level
            ip_bans[ip]['permanent'] = True
            ip_bans[ip]['ban_until'] = float('inf')
        else:
            ip_bans[ip]['level'] = next_level
            ip_bans[ip]['ban_until'] = time.time() + BAN_STAGES[next_level]


def init_security(app):
    """
    Initialise toutes les protections sur l'application Flask
    """
    
    @app.before_request
    def filter_requests():
        client_ip = request.remote_addr
        
        # 1. VÉRIFICATION DU BANNISSEMENT
        if client_ip in ip_bans:
            ban_info = ip_bans[client_ip]
            if ban_info['permanent']:
                return jsonify({"error": "Votre IP a été bannie définitivement pour comportement abusif."}), 403
            
            if time.time() < ban_info['ban_until']:
                remaining_time = int((ban_info['ban_until'] - time.time()) // 60)
                return jsonify({"error": f"IP temporairement bloquée. Réessayez dans {remaining_time} minutes."}), 429

        # 2. VÉRIFICATION DE LA CLÉ INTERNE (Gateway -> Microservice)
        # Harmonisé avec le Gateway : header 'X-Internal-Key' et variable 'TAKO_INTERNAL_API_KEY'
        internal_key = request.headers.get("X-Internal-Key")
        expected_key =  os.getenv("TAKO_API_KEY")

        if not internal_key or internal_key != expected_key:
            return jsonify({"error": "Accès refusé. Clé serveur interne invalide ou manquante."}), 401

        # 3. PROTECTION DDOS & BRUTE-FORCE (Pour les accès hors Gateway IP)
        gateway_ip = os.getenv("GATEWAY_IP")
        if client_ip != gateway_ip:
            current_time = time.time()
            if client_ip not in ip_requests:
                ip_requests[client_ip] = []
            
            ip_requests[client_ip] = [t for t in ip_requests[client_ip] if current_time - t < RATE_LIMIT_WINDOW]
            
            if len(ip_requests[client_ip]) >= RATE_LIMIT:
                register_infraction(client_ip)
                ban_level = ip_bans[client_ip]['level']
                ban_minutes = BAN_STAGES[ban_level] // 60
                return jsonify({"error": f"Brute-force détecté. IP bloquée pour {ban_minutes} minutes."}), 429
            
            ip_requests[client_ip].append(current_time)

        # 4. PARE-FEU WAF (Injection SQL)
        def check_sqli(value):
            if value and SQLI_PATTERN.search(str(value)):
                register_infraction(client_ip)
                return True
            return False

        for _, value in request.args.items():
            if check_sqli(value):
                return jsonify({"error": "Requête malveillante détectée. IP pénalisée."}), 400
                
        if request.is_json:
            try:
                data = str(request.get_json(silent=True))
                if check_sqli(data):
                    return jsonify({"error": "Requête malveillante détectée. IP pénalisée."}), 400
            except Exception:
                pass
                
        for _, value in request.form.items():
            if check_sqli(value):
                return jsonify({"error": "Requête malveillante détectée. IP pénalisée."}), 400


def is_safe_image(file):
    if not file or not file.filename:
        return False, "Aucun fichier fourni."

    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0) 
    
    if file_size > MAX_FILE_SIZE:
        return False, "Fichier trop volumineux (5 Mo max)."

    filename = secure_filename(file.filename)
    
    if filename.count('.') > 1:
        return False, "Les doubles extensions sont interdites."
        
    if '.' not in filename:
        return False, "Le fichier n'a pas d'extension."
        
    ext = filename.rsplit('.', 1)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return False, f"Extension '.{ext}' non autorisée."
    
    return True, filename