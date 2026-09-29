"""Client-only SMS authentication. Legacy driver password endpoints are unchanged."""
import base64
import hashlib
import hmac
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from flask import Blueprint, jsonify, request
from werkzeug.security import generate_password_hash

from src.data import Database
from src.routes.client_api import _role, _secret, _token

phone_bp = Blueprint('client_phone_auth', __name__, url_prefix='/api/v1/auth/otp')
PHONE = re.compile(r'^\+[1-9][0-9]{7,14}$')


def _hash(tel, code):
    return hmac.new(_secret().encode(), f'{tel}:{code}'.encode(), hashlib.sha256).hexdigest()


def _send_sms(tel, code):
    sid = os.environ.get('TWILIO_ACCOUNT_SID')
    token = os.environ.get('TWILIO_AUTH_TOKEN')
    sender = os.environ.get('TWILIO_FROM_NUMBER')
    if not all((sid, token, sender)):
        raise RuntimeError('Fournisseur SMS non configuré')
    body = urlencode({
        'To': tel, 'From': sender,
        'Body': f'Votre code Tako est {code}. Il expire dans 5 minutes.'
    }).encode()
    auth = base64.b64encode(f'{sid}:{token}'.encode()).decode()
    req = Request(
        f'https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json',
        data=body, headers={
            'Authorization': f'Basic {auth}',
            'Content-Type': 'application/x-www-form-urlencoded'
        }, method='POST')
    with urlopen(req, timeout=10) as response:
        if response.status not in (200, 201):
            raise RuntimeError('Envoi SMS refusé')


@phone_bp.post('/request')
def request_code():
    data = request.get_json(silent=True) or {}
    tel = str(data.get('tel') or '').strip()
    if not PHONE.fullmatch(tel):
        return jsonify(message='Numéro au format international requis.'), 400
    try:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        code = f'{secrets.randbelow(1_000_000):06d}'
        with Database() as cursor:
            cursor.execute('SELECT sent_at FROM client_phone_codes WHERE tel=%s FOR UPDATE', (tel,))
            row = cursor.fetchone()
            if row and row['sent_at'] > now - timedelta(seconds=60):
                return jsonify(message='Patientez une minute avant un nouveau code.'), 429
            cursor.execute(
                'INSERT INTO client_phone_codes (tel, code_hash, expires_at, sent_at, attempts) '
                'VALUES (%s,%s,%s,%s,0) ON DUPLICATE KEY UPDATE '
                'code_hash=VALUES(code_hash), expires_at=VALUES(expires_at), '
                'sent_at=VALUES(sent_at), attempts=0',
                (tel, _hash(tel, code), now + timedelta(minutes=5), now))
            _send_sms(tel, code)
    except (RuntimeError, HTTPError, URLError, TimeoutError, OSError):
        return jsonify(message='Envoi SMS indisponible. Réessayez plus tard.'), 503
    return jsonify(message='Si le numéro est joignable, un code a été envoyé.'), 202


@phone_bp.post('/verify')
def verify_code():
    data = request.get_json(silent=True) or {}
    tel = str(data.get('tel') or '').strip()
    code = str(data.get('code') or '').strip()
    nom = str(data.get('nom') or '').strip()
    prenom = str(data.get('prenom') or '').strip()
    if not PHONE.fullmatch(tel) or not re.fullmatch(r'[0-9]{6}', code):
        return jsonify(message='Numéro ou code invalide.'), 400
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with Database() as cursor:
        cursor.execute('SELECT code_hash, expires_at, attempts FROM client_phone_codes '
                       'WHERE tel=%s FOR UPDATE', (tel,))
        challenge = cursor.fetchone()
        if not challenge or challenge['expires_at'] <= now or challenge['attempts'] >= 5:
            return jsonify(message='Code expiré. Demandez un nouveau code.'), 401
        if not hmac.compare_digest(challenge['code_hash'], _hash(tel, code)):
            cursor.execute('UPDATE client_phone_codes SET attempts=attempts+1 WHERE tel=%s', (tel,))
            return jsonify(message='Code invalide.'), 401
        role = _role()
        cursor.execute('SELECT u.id_user, cp.nom, cp.prenom FROM user u '
                       'LEFT JOIN client_profiles cp ON cp.user_id=u.id_user '
                       'WHERE u.tel=%s AND u.id_tpcompte=%s', (tel, role))
        user = cursor.fetchone()
        if user is None:
            if not nom or not prenom or len(nom) > 100 or len(prenom) > 100:
                return jsonify(message='Nom et prénom requis pour créer le compte.'), 422
            # Legacy user.password is NOT NULL. Store a random unusable secret;
            # the client never sees, chooses, or authenticates with it.
            cursor.execute('INSERT INTO user (tel,password,id_tpcompte,date_creation) '
                           'VALUES (%s,%s,%s,%s)',
                           (tel, generate_password_hash(secrets.token_urlsafe(48)), role, now))
            user_id = cursor.lastrowid
            cursor.execute('INSERT INTO client_profiles (user_id,nom,prenom) VALUES (%s,%s,%s)',
                           (user_id, nom, prenom))
        else:
            user_id, nom, prenom = user['id_user'], user['nom'], user['prenom']
        cursor.execute('DELETE FROM client_phone_codes WHERE tel=%s', (tel,))
    return jsonify(access_token=_token(user_id),
                   user={'id': user_id, 'tel': tel, 'nom': nom, 'prenom': prenom})
