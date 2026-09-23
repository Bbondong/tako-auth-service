"""Versioned client API. All account-scoped queries use the verified JWT subject."""
import os
from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from flask import Blueprint, g, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

from src.data import Database, execute_query, fetch_all, fetch_one

client_bp = Blueprint('client_api', __name__, url_prefix='/api/v1')


def _secret():
    secret = os.getenv('TAKO_JWT_SECRET')
    if not secret or len(secret) < 32:
        raise RuntimeError('TAKO_JWT_SECRET must contain at least 32 characters')
    return secret


def _role():
    role = os.getenv('TAKO_CLIENT_ROLE_ID')
    if not role or not role.isdigit():
        raise RuntimeError('TAKO_CLIENT_ROLE_ID must match the existing client role in id_tpcompte')
    return int(role)


def _token(user_id):
    now = datetime.now(timezone.utc)
    return jwt.encode({'sub': str(user_id), 'role': 'client', 'iat': now,
                       'exp': now + timedelta(hours=12)}, _secret(), algorithm='HS256')


def authenticated(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        authorization = request.headers.get('Authorization', '')
        if not authorization.startswith('Bearer '):
            return jsonify(message='Authentification requise.'), 401
        try:
            claims = jwt.decode(authorization[7:], _secret(), algorithms=['HS256'],
                                options={'require': ['sub', 'exp', 'iat']})
            user_id = int(claims['sub'])
            if user_id <= 0 or claims.get('role') != 'client':
                raise ValueError('invalid subject')
            user = fetch_one('SELECT id_user FROM user WHERE id_user=%s AND id_tpcompte=%s',
                             (user_id, _role()))
            if not user:
                return jsonify(message='Compte introuvable.'), 401
            g.user_id = user_id
        except (jwt.InvalidTokenError, ValueError, TypeError):
            return jsonify(message='Session expirée ou invalide.'), 401
        return fn(*args, **kwargs)
    return wrapper


@client_bp.post('/auth/register')
def register_client():
    # Validate deployment configuration before inserting a user.
    _secret()
    role = _role()
    data = request.get_json(silent=True) or {}
    tel = str(data.get('tel', '')).strip()
    nom = str(data.get('nom', '')).strip()
    prenom = str(data.get('prenom', '')).strip()
    password = data.get('password', '')
    if not tel or not nom or not prenom or not isinstance(password, str) or len(password) < 8:
        return jsonify(message='Téléphone, nom, prénom et mot de passe (8 caractères minimum) requis.'), 400
    if len(tel) > 25 or len(nom) > 100 or len(prenom) > 100:
        return jsonify(message='Champ trop long.'), 400
    if fetch_one('SELECT id_user FROM user WHERE tel=%s', (tel,)):
        return jsonify(message='Ce téléphone est déjà utilisé.'), 409
    try:
        with Database() as cursor:
            cursor.execute('INSERT INTO user (tel, password, id_tpcompte, date_creation) VALUES (%s,%s,%s,%s)',
                           (tel, generate_password_hash(password), role, datetime.now(timezone.utc)))
            user_id = cursor.lastrowid
            cursor.execute('INSERT INTO client_profiles (user_id, nom, prenom) VALUES (%s,%s,%s)',
                           (user_id, nom, prenom))
    except Exception:
        # A concurrent registration can race the duplicate check; unique tel constraint is required.
        return jsonify(message="Inscription impossible. Vérifiez la configuration et réessayez."), 500
    return jsonify(user={'id': user_id, 'tel': tel, 'nom': nom, 'prenom': prenom},
                   access_token=_token(user_id)), 201


@client_bp.post('/auth/login')
def login_client():
    data = request.get_json(silent=True) or {}
    tel = str(data.get('tel', '')).strip()
    password = data.get('password')
    if not tel or not isinstance(password, str) or not password:
        return jsonify(message='Téléphone et mot de passe requis.'), 400
    user = fetch_one('SELECT u.id_user, u.tel, u.password, cp.nom, cp.prenom FROM user u '
                     'JOIN client_profiles cp ON cp.user_id=u.id_user '
                     'WHERE u.tel=%s AND u.id_tpcompte=%s', (tel, _role()))
    if not user or not check_password_hash(user['password'], password):
        return jsonify(message='Identifiants incorrects.'), 401
    return jsonify(access_token=_token(user['id_user']),
                   user={'id': user['id_user'], 'tel': user['tel'],
                         'nom': user['nom'], 'prenom': user['prenom']})


@client_bp.get('/me')
@authenticated
def me():
    user = fetch_one('SELECT u.id_user AS id, u.tel, cp.nom, cp.prenom FROM user u '
                     'JOIN client_profiles cp ON cp.user_id=u.id_user WHERE u.id_user=%s', (g.user_id,))
    return jsonify(user=user)


@client_bp.route('/favorites', methods=['GET', 'POST'])
@authenticated
def favorites():
    if request.method == 'GET':
        return jsonify(favorites=fetch_all('SELECT id, title, address, latitude, longitude, created_at '
                                          'FROM favorite_locations WHERE user_id=%s ORDER BY created_at DESC',
                                          (g.user_id,)))
    data = request.get_json(silent=True) or {}
    title, address = str(data.get('title', '')).strip(), str(data.get('address', '')).strip()
    try:
        lat, lon = float(data['latitude']), float(data['longitude'])
    except (ValueError, TypeError, KeyError):
        return jsonify(message='Coordonnées invalides.'), 400
    import math
    if not title or not address or len(title) > 100 or len(address) > 500 or not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
        return jsonify(message='Lieu ou coordonnées invalides.'), 400
    favorite_id = execute_query('INSERT INTO favorite_locations (user_id,title,address,latitude,longitude) '
                                'VALUES (%s,%s,%s,%s,%s)', (g.user_id, title, address, lat, lon))
    return jsonify(id=favorite_id, title=title, address=address, latitude=lat, longitude=lon), 201


@client_bp.delete('/favorites/<int:favorite_id>')
@authenticated
def delete_favorite(favorite_id):
    with Database() as cursor:
        count = cursor.execute('DELETE FROM favorite_locations WHERE id=%s AND user_id=%s',
                               (favorite_id, g.user_id))
    if not count:
        return jsonify(message='Lieu introuvable.'), 404
    return '', 204


@client_bp.get('/courses')
@authenticated
def courses():
    return jsonify(courses=fetch_all('SELECT id, pickup, dropoff, price, status, driver_name, vehicle, '
                                    'created_at FROM courses WHERE user_id=%s ORDER BY created_at DESC',
                                    (g.user_id,)))


@client_bp.route('/courses', methods=['POST'])
@authenticated
def create_course():
    data = request.get_json(silent=True) or {}
    pickup, dropoff = str(data.get('pickup', '')).strip(), str(data.get('dropoff', '')).strip()
    cargo_type = str(data.get('cargo_type', '')).strip()
    try:
        lat1, lon1 = float(data['pickup_latitude']), float(data['pickup_longitude'])
        lat2, lon2 = float(data['destination_latitude']), float(data['destination_longitude'])
        weight = float(data['weight'])
    except (KeyError, ValueError, TypeError):
        return jsonify(message='Coordonnées ou poids invalides.'), 400
    import math
    if not pickup or not dropoff or not cargo_type or len(pickup) > 500 or len(dropoff) > 500 or len(cargo_type) > 100 or not all(map(math.isfinite, [lat1, lon1, lat2, lon2, weight])) or weight <= 0 or not (-90 <= lat1 <= 90 and -90 <= lat2 <= 90 and -180 <= lon1 <= 180 and -180 <= lon2 <= 180):
        return jsonify(message='Informations de course invalides.'), 400
    dimensions = []
    for key in ('length', 'width', 'height'):
        value = data.get(key)
        try:
            number = float(value) if value is not None else None
            if number is not None and (not math.isfinite(number) or number <= 0):
                raise ValueError()
            dimensions.append(number)
        except (ValueError, TypeError):
            return jsonify(message='Dimensions invalides.'), 400
    description = str(data.get('description') or '').strip()[:2000]
    photo_url = None
    if data.get('photo_base64'):
        import base64
        import cloudinary.uploader
        photo = data['photo_base64']
        if not isinstance(photo, str) or len(photo) > 7_000_000:
            return jsonify(message='Photo trop volumineuse.'), 400
        try:
            raw = base64.b64decode(photo, validate=True)
            if len(raw) > 5_000_000 or not (raw.startswith(b'\xff\xd8\xff') or raw.startswith(b'\x89PNG\r\n\x1a\n')):
                return jsonify(message='Photo invalide (JPEG ou PNG, 5 Mo max).'), 400
            mime = 'image/jpeg' if raw.startswith(b'\xff') else 'image/png'
            photo_url = cloudinary.uploader.upload('data:%s;base64,%s' % (mime, photo),
                                                   folder='tako/cargo', resource_type='image')['secure_url']
        except Exception:
            return jsonify(message='Téléversement de la photo impossible.'), 503
    with Database() as cursor:
        cursor.execute('INSERT INTO courses (user_id,pickup,dropoff,pickup_latitude,pickup_longitude,'
                       'destination_latitude,destination_longitude,cargo_type,weight,description,'
                       'length_cm,width_cm,height_cm,is_fragile,is_express,photo_url,status) '
                       "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending')",
                       (g.user_id, pickup, dropoff, lat1, lon1, lat2, lon2, cargo_type, weight,
                        description, *dimensions, bool(data.get('is_fragile')),
                        bool(data.get('is_express')), photo_url))
        course_id = cursor.lastrowid
        cursor.execute('INSERT INTO course_positions '
                       '(course_id, actor, user_id, latitude, longitude) '
                       "VALUES (%s,'client',%s,%s,%s)", (course_id, g.user_id, lat1, lon1))
    return jsonify(id=course_id, status='pending'), 201


@client_bp.get('/courses/<int:course_id>')
@authenticated
def course_detail(course_id):
    course = fetch_one('SELECT id, pickup, dropoff, status, driver_name, vehicle, '
                       'driver_latitude, driver_longitude, price, created_at FROM courses '
                       'WHERE id=%s AND user_id=%s', (course_id, g.user_id))
    if not course:
        return jsonify(message='Course introuvable.'), 404
    return jsonify(course=course)


@client_bp.get('/cargo-types')
def cargo_types():
    return jsonify(types=[{'label': row['label']} for row in fetch_all(
        'SELECT label FROM cargo_types WHERE active=1 ORDER BY sort_order, label')])


@client_bp.get('/payment-methods')
@authenticated
def payment_methods():
    return jsonify(methods=fetch_all('SELECT id, title, details FROM payment_methods WHERE user_id=%s',
                                    (g.user_id,)))
