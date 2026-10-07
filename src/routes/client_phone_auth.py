"""Client-only SMS authentication. Legacy driver password endpoints are unchanged."""
import hashlib
import hmac
import json
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from flask import Blueprint, jsonify, request
from werkzeug.security import generate_password_hash

from src.data import Database
from src.routes.client_api import _role, _secret, _token

phone_bp = Blueprint('client_phone_auth', __name__, url_prefix='/api/v1/auth/otp')
WHATSAPP_OTP_URL = 'https://benbot.alwaysdata.net/send-otp'
PHONE = re.compile(r'^\+[1-9][0-9]{7,14}$')


def _hash(tel, code):
    return hmac.new(_secret().encode(), f'{tel}:{code}'.encode(), hashlib.sha256).hexdigest()


def _send_sms(tel, code):
    """Send the OTP through the WhatsApp microservice (raises on any failure)."""
    secret = os.environ.get('WHATSAPP_API_SECRET')
    if not secret:
        raise RuntimeError('Fournisseur OTP WhatsApp non configuré')
    payload = json.dumps({
        'secret': secret,
        'phone': re.sub(r'\D', '', tel),
        'code': code
    }).encode()
    req = Request(WHATSAPP_OTP_URL, data=payload,
                  headers={'Content-Type': 'application/json'}, method='POST')
    with urlopen(req, timeout=10) as response:
        body = json.loads(response.read() or b'{}')
        if response.status != 200 or not body.get('success'):
            raise RuntimeError('Envoi OTP refusé')


def _register_client(cursor, tel, nom, prenom, sexe, role, now):
    """Create an INACTIVE Client account in the shared user/user_info tables.

    The account only becomes active once the WhatsApp code is verified.
    Required driver-only fields (adresse, matricul, permis) are filled with a
    unique 'client-<id>' placeholder; sexe is one letter (M/F); the profile
    photo and postnom are stored as NULL.
    """
    # Legacy user.password is NOT NULL. Store a random unusable secret;
    # the client never sees, chooses, or authenticates with it.
    cursor.execute('INSERT INTO user (tel,password,id_tpcompte,date_creation,active) '
                   'VALUES (%s,%s,%s,%s,0)',
                   (tel, generate_password_hash(secrets.token_urlsafe(48)), role, now))
    user_id = cursor.lastrowid
    placeholder = f'client-{user_id}'
    cursor.execute('INSERT INTO user_info (nom,postnom,prenom,sexe,adresse,matricul,profil,permis,id_user) '
                   'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                   (nom, None, prenom, sexe, placeholder, placeholder, None, placeholder, user_id))
    return user_id


def _issue_code(cursor, tel, now):
    """Store a fresh hashed 6-digit code and send it; None if allowed, else a 429 response."""
    cursor.execute('SELECT sent_at FROM client_phone_codes WHERE tel=%s FOR UPDATE', (tel,))
    row = cursor.fetchone()
    if row and row['sent_at'] > now - timedelta(seconds=60):
        return jsonify(message='Patientez une minute avant un nouveau code.'), 429
    code = f'{secrets.randbelow(1_000_000):06d}'
    cursor.execute(
        'INSERT INTO client_phone_codes (tel, code_hash, expires_at, sent_at, attempts) '
        'VALUES (%s,%s,%s,%s,0) ON DUPLICATE KEY UPDATE '
        'code_hash=VALUES(code_hash), expires_at=VALUES(expires_at), '
        'sent_at=VALUES(sent_at), attempts=0',
        (tel, _hash(tel, code), now + timedelta(minutes=5), now))
    _send_sms(tel, code)
    return None


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


@phone_bp.post('/register')
def register():
    """Sign-up: create the account inactive, then send the code by WhatsApp."""
    data = request.get_json(silent=True) or {}
    tel = str(data.get('tel') or '').strip()
    nom = str(data.get('nom') or '').strip()
    prenom = str(data.get('prenom') or '').strip()
    sexe = str(data.get('sexe') or 'M').strip().upper()
    if not PHONE.fullmatch(tel):
        return jsonify(message='Numéro au format international requis.'), 400
    if not nom or not prenom or len(nom) > 100 or len(prenom) > 100:
        return jsonify(message='Nom et prénom requis.'), 422
    if sexe not in ('M', 'F'):
        return jsonify(message='Sexe invalide : M ou F.'), 422
    try:
        now = _now()
        with Database() as cursor:
            cursor.execute('SELECT id_user, active FROM user WHERE tel=%s AND id_tpcompte=%s '
                           'FOR UPDATE', (tel, _role()))
            user = cursor.fetchone()
            if user and user['active']:
                return jsonify(message='Ce numéro est déjà inscrit. Connectez-vous.'), 409
            blocked = _issue_code(cursor, tel, now)
            if blocked:
                return blocked
            if user:
                cursor.execute('UPDATE user_info SET nom=%s, prenom=%s, sexe=%s WHERE id_user=%s',
                               (nom, prenom, sexe, user['id_user']))
            else:
                _register_client(cursor, tel, nom, prenom, sexe, _role(), now)
    except (RuntimeError, ValueError, HTTPError, URLError, TimeoutError, OSError):
        return jsonify(message='Envoi du code indisponible. Réessayez plus tard.'), 503
    return jsonify(message='Un code de vérification a été envoyé par WhatsApp.'), 202


@phone_bp.post('/request')
def request_code():
    """Login / resend: send a code to an already registered client."""
    data = request.get_json(silent=True) or {}
    tel = str(data.get('tel') or '').strip()
    if not PHONE.fullmatch(tel):
        return jsonify(message='Numéro au format international requis.'), 400
    try:
        with Database() as cursor:
            cursor.execute('SELECT id_user FROM user WHERE tel=%s AND id_tpcompte=%s',
                           (tel, _role()))
            if cursor.fetchone() is None:
                return jsonify(message='Aucun compte pour ce numéro. Inscrivez-vous.'), 404
            blocked = _issue_code(cursor, tel, _now())
            if blocked:
                return blocked
    except (RuntimeError, ValueError, HTTPError, URLError, TimeoutError, OSError):
        return jsonify(message='Envoi du code indisponible. Réessayez plus tard.'), 503
    return jsonify(message='Un code de vérification a été envoyé par WhatsApp.'), 202


@phone_bp.post('/verify-code')
@phone_bp.post('/verify')
def verify_code():
    """Check the code; on success activate the account and return the access token."""
    data = request.get_json(silent=True) or {}
    tel = str(data.get('tel') or '').strip()
    code = str(data.get('code') or '').strip()
    if not PHONE.fullmatch(tel) or not re.fullmatch(r'[0-9]{6}', code):
        return jsonify(message='Numéro ou code invalide.'), 400
    now = _now()
    with Database() as cursor:
        cursor.execute('SELECT code_hash, expires_at, attempts FROM client_phone_codes '
                       'WHERE tel=%s FOR UPDATE', (tel,))
        challenge = cursor.fetchone()
        if not challenge or challenge['expires_at'] <= now or challenge['attempts'] >= 5:
            return jsonify(message='Code expiré. Demandez un nouveau code.'), 401
        if not hmac.compare_digest(challenge['code_hash'], _hash(tel, code)):
            cursor.execute('UPDATE client_phone_codes SET attempts=attempts+1 WHERE tel=%s', (tel,))
            return jsonify(message='Code invalide.'), 401
        cursor.execute('SELECT u.id_user, ui.nom, ui.prenom, ui.profil FROM user u '
                       'LEFT JOIN user_info ui ON ui.id_user=u.id_user '
                       'WHERE u.tel=%s AND u.id_tpcompte=%s', (tel, _role()))
        user = cursor.fetchone()
        if user is None:
            return jsonify(message='Aucun compte pour ce numéro. Inscrivez-vous.'), 404
        cursor.execute('UPDATE user SET active=1 WHERE id_user=%s', (user['id_user'],))
        cursor.execute('DELETE FROM client_phone_codes WHERE tel=%s', (tel,))
    return jsonify(access_token=_token(user['id_user']),
                   user={'id': user['id_user'], 'tel': tel, 'nom': user['nom'],
                         'prenom': user['prenom'], 'role': 'client', 'profil': user['profil']})
