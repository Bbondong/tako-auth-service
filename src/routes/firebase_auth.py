"""Exchange a verified Firebase phone ID token for the existing Tako client JWT."""
import re
import secrets
from datetime import datetime, timezone

from firebase_admin import auth, exceptions as firebase_exceptions
from flask import Blueprint, current_app, jsonify, request
from pymysql import MySQLError, IntegrityError
from werkzeug.security import generate_password_hash

from src.data import Database
from src.routes.client_api import _role, _secret, _token

firebase_bp = Blueprint('firebase_auth', __name__, url_prefix='/api/v1/auth')
PHONE = re.compile(r'^\+[1-9][0-9]{7,14}$')


def _client_session(tel, nom, prenom, role):
    with Database() as cursor:
        # Query all roles first: never convert a driver account into a client.
        cursor.execute('SELECT u.id_user, u.id_tpcompte, cp.nom, cp.prenom '
                       'FROM user u LEFT JOIN client_profiles cp ON cp.user_id=u.id_user '
                       'WHERE u.tel=%s FOR UPDATE', (tel,))
        user = cursor.fetchone()
        if user and int(user['id_tpcompte']) != role:
            return {'message': 'Ce numéro appartient à un autre type de compte.'}, 403
        if not user or not user['nom'] or not user['prenom']:
            if not nom or not prenom:
                return {'message': 'Nom et prénom requis pour créer le compte.',
                        'code': 'profile_required'}, 422
            if not user:
                # user.password is NOT NULL in the shared legacy schema.
                # This random secret cannot be chosen or used by the client.
                cursor.execute('INSERT INTO user (tel,password,id_tpcompte,date_creation) '
                               'VALUES (%s,%s,%s,%s)',
                               (tel, generate_password_hash(secrets.token_urlsafe(48)), role,
                                datetime.now(timezone.utc).replace(tzinfo=None)))
                user_id = cursor.lastrowid
            else:
                user_id = user['id_user']
            cursor.execute('INSERT INTO client_profiles (user_id,nom,prenom) VALUES (%s,%s,%s) '
                           'ON DUPLICATE KEY UPDATE nom=VALUES(nom), prenom=VALUES(prenom)',
                           (user_id, nom, prenom))
        else:
            user_id, nom, prenom = user['id_user'], user['nom'], user['prenom']
        # Issue before committing: invalid JWT configuration must roll back creation.
        token = _token(user_id)
    return {'access_token': token,
            'user': {'id': user_id, 'tel': tel, 'nom': nom, 'prenom': prenom}}, 200


@firebase_bp.post('/firebase-login')
def firebase_login():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(message='Un corps JSON valide est requis.'), 400
    id_token = data.get('id_token')
    if not isinstance(id_token, str) or not id_token.strip() or len(id_token) > 16384:
        return jsonify(message='Jeton Firebase requis.'), 400
    names = []
    for key in ('nom', 'prenom'):
        value = data.get(key, '')
        if value is None:
            value = ''
        if not isinstance(value, str) or len(value.strip()) > 100:
            return jsonify(message='Nom et prénom invalides (100 caractères maximum).'), 400
        names.append(value.strip())
    firebase_app = current_app.extensions.get('tako_firebase')
    if firebase_app is None:
        return jsonify(message='Authentification Firebase non configurée sur le serveur.'), 503
    try:
        claims = auth.verify_id_token(id_token, app=firebase_app, check_revoked=True)
    except auth.ExpiredIdTokenError:
        return jsonify(message='Session Firebase expirée. Vérifiez de nouveau votre numéro.'), 401
    except (auth.RevokedIdTokenError, auth.UserDisabledError):
        return jsonify(message='Session Firebase révoquée ou compte désactivé.'), 401
    except auth.CertificateFetchError:
        return jsonify(message='Vérification Firebase indisponible. Réessayez.'), 503
    except (auth.InvalidIdTokenError, ValueError):
        return jsonify(message='Jeton Firebase invalide. Vérifiez de nouveau votre numéro.'), 401
    except firebase_exceptions.FirebaseError:
        current_app.logger.warning('Service de vérification Firebase indisponible.')
        return jsonify(message='Vérification Firebase indisponible. Réessayez.'), 503
    tel = claims.get('phone_number')
    firebase_claim = claims.get('firebase') or {}
    if (not isinstance(tel, str) or not PHONE.fullmatch(tel)
            or not isinstance(firebase_claim, dict)
            or firebase_claim.get('sign_in_provider') != 'phone'):
        return jsonify(message='Une authentification Firebase par téléphone est requise.'), 401
    try:
        role = _role()
        _secret()
        # Requires the existing unique index on user.tel. Retry a competing creation
        # after rollback rather than creating a second client or returning a 500.
        for attempt in range(2):
            try:
                payload, status = _client_session(tel, *names, role)
                return jsonify(**payload), status
            except IntegrityError as error:
                if error.args[0] != 1062 or attempt:
                    raise
    except (MySQLError, RuntimeError, ValueError):
        current_app.logger.error('Connexion client Firebase impossible : base ou configuration indisponible.')
        return jsonify(message='Connexion Tako indisponible. Réessayez plus tard.'), 503
