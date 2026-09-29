"""Location exchange scoped to a course and its authenticated participants."""
import math
import os
from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from flask import Blueprint, g, jsonify, request

from src.data import Database, fetch_all, fetch_one
from src.routes.client_api import _secret, _role, authenticated
from src.services.auth_service import login_user

positions_bp = Blueprint('course_positions', __name__, url_prefix='/api/v1')


def _driver_role():
    value = os.getenv('TAKO_DRIVER_ROLE_ID')
    if not value or not value.isdigit() or int(value) == _role():
        raise RuntimeError('TAKO_DRIVER_ROLE_ID must be a distinct, existing driver role')
    return int(value)


def driver_authenticated(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        header = request.headers.get('Authorization', '')
        if not header.startswith('Bearer '):
            return jsonify(message='Authentification chauffeur requise.'), 401
        try:
            claims = jwt.decode(header[7:], _secret(), algorithms=['HS256'],
                                options={'require': ['sub', 'exp', 'iat']})
            driver_id = int(claims['sub'])
            if driver_id <= 0 or claims.get('role') != 'driver':
                raise ValueError('Invalid driver')
            user = fetch_one('SELECT id_user FROM user WHERE id_user=%s AND id_tpcompte=%s',
                             (driver_id, _driver_role()))
            if not user:
                return jsonify(message='Compte chauffeur introuvable.'), 401
            g.user_id = driver_id
        except (jwt.InvalidTokenError, ValueError, TypeError):
            return jsonify(message='Session chauffeur expirée ou invalide.'), 401
        return fn(*args, **kwargs)
    return wrapper


def _coordinates(data):
    # GeoJSON convention: x = longitude, y = latitude. Flutter sends explicit names.
    try:
        latitude = float(data['latitude'])
        longitude = float(data['longitude'])
    except (KeyError, TypeError, ValueError):
        return None
    if not (math.isfinite(latitude) and math.isfinite(longitude) and
            -90 <= latitude <= 90 and -180 <= longitude <= 180):
        return None
    return latitude, longitude


def _positions(course_id):
    rows = fetch_all('SELECT actor, latitude, longitude, updated_at FROM course_positions '
                     'WHERE course_id=%s', (course_id,))
    return {row['actor']: {'latitude': float(row['latitude']),
                           'longitude': float(row['longitude']),
                           'updated_at': row['updated_at'].isoformat()
                           if isinstance(row['updated_at'], datetime)
                           else str(row['updated_at'])} for row in rows}


def _course(course_id, role):
    field = 'user_id' if role == 'client' else 'driver_user_id'
    return fetch_one(f'SELECT id, user_id, driver_user_id, status, driver_name, vehicle, '
                     f'price, pickup, dropoff, pickup_latitude, pickup_longitude, destination_latitude, '
                     f'destination_longitude FROM courses WHERE id=%s AND {field}=%s', (course_id, g.user_id))


def _snapshot(course):
    return jsonify(course={'id': course['id'], 'status': course['status'],
                           'driver_name': course['driver_name'], 'vehicle': course['vehicle'],
                           'price': course['price'], 'pickup': course['pickup'], 'dropoff': course['dropoff'],
                           'pickup_latitude': float(course['pickup_latitude']),
                           'pickup_longitude': float(course['pickup_longitude']),
                           'destination_latitude': float(course['destination_latitude']),
                           'destination_longitude': float(course['destination_longitude'])},
                   positions=_positions(course['id']))


@positions_bp.post('/driver/auth/login')
def driver_login():
    data = request.get_json(silent=True) or {}
    identifier = str(data.get('identifier') or data.get('tel') or '').strip()
    password = data.get('password')
    if not identifier or not isinstance(password, str) or not password:
        return jsonify(message='Identifiant et mot de passe requis.'), 400
    user, auth_error = login_user(identifier, password)
    if auth_error or user is None or user['id_tpcompte'] != _driver_role():
        return jsonify(message='Identifiants incorrects.'), 401
    now = datetime.now(timezone.utc)
    token = jwt.encode({'sub': str(user['id_user']), 'role': 'driver',
                        'iat': now, 'exp': now + timedelta(hours=12)},
                       _secret(), algorithm='HS256')
    return jsonify(access_token=token, user_id=user['id_user'])


def _distance_km(lat1, lon1, lat2, lon2):
    a1, a2 = math.radians(float(lat1)), math.radians(float(lat2))
    d_lat = a2 - a1
    d_lon = math.radians(float(lon2) - float(lon1))
    h = math.sin(d_lat / 2) ** 2 + math.cos(a1) * math.cos(a2) * math.sin(d_lon / 2) ** 2
    return 6371 * 2 * math.asin(min(1, math.sqrt(h)))


@positions_bp.put('/driver/presence')
@driver_authenticated
def update_presence():
    data = request.get_json(silent=True) or {}
    point = _coordinates(data)
    if point is None or not isinstance(data.get('available'), bool):
        return jsonify(message='Position et disponibilité requises.'), 400
    with Database() as cursor:
        cursor.execute('SELECT driver_user_id FROM driver_presence '
                       'WHERE driver_user_id=%s FOR UPDATE', (g.user_id,))
        cursor.execute("SELECT id FROM courses WHERE driver_user_id=%s "
                       "AND status IN ('assigned','arrived','in_transit') LIMIT 1",
                       (g.user_id,))
        active = cursor.fetchone()
        available = data['available'] and active is None
        cursor.execute(
            'INSERT INTO driver_presence (driver_user_id, latitude, longitude, available) '
            'VALUES (%s,%s,%s,%s) ON DUPLICATE KEY UPDATE '
            'latitude=VALUES(latitude), longitude=VALUES(longitude), '
            'available=VALUES(available), updated_at=CURRENT_TIMESTAMP(3)',
            (g.user_id, *point, available))
    return jsonify(available=available)


@positions_bp.get('/driver/courses/active')
@driver_authenticated
def active_driver_course():
    row = fetch_one("SELECT id FROM courses WHERE driver_user_id=%s "
                    "AND status IN ('assigned','arrived','in_transit') "
                    "ORDER BY id DESC LIMIT 1", (g.user_id,))
    if not row:
        return jsonify(course=None)
    return _snapshot(_course(row['id'], 'driver'))


@positions_bp.get('/driver/courses/available')
@driver_authenticated
def available_courses():
    presence = fetch_one(
        'SELECT latitude, longitude, available, updated_at FROM driver_presence '
        'WHERE driver_user_id=%s', (g.user_id,))
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if not presence or not presence['available'] or presence['updated_at'] < now - timedelta(seconds=30):
        return jsonify(courses=[])
    latitude, longitude = float(presence['latitude']), float(presence['longitude'])
    # Bound the SQL scan, then rank by actual great-circle distance.
    lon_span = 0.15 / max(0.2, math.cos(math.radians(latitude)))
    rows = fetch_all(
        'SELECT id, pickup, dropoff, pickup_latitude, pickup_longitude, '
        'destination_latitude, destination_longitude, cargo_type, weight, '
        'price, created_at FROM courses '
        "WHERE status='pending' AND driver_user_id IS NULL "
        'AND pickup_latitude BETWEEN %s AND %s '
        'AND pickup_longitude BETWEEN %s AND %s '
        'ORDER BY created_at DESC LIMIT 200',
        (latitude - 0.15, latitude + 0.15, longitude - lon_span, longitude + lon_span))
    for row in rows:
        row['distance_km'] = round(_distance_km(
            latitude, longitude, row['pickup_latitude'], row['pickup_longitude']), 1)
    return jsonify(courses=sorted(
        (row for row in rows if row['distance_km'] <= 15),
        key=lambda row: row['distance_km']))


@positions_bp.post('/driver/courses/<int:course_id>/accept')
@driver_authenticated
def accept_course(course_id):
    point = _coordinates(request.get_json(silent=True) or {})
    if point is None:
        return jsonify(message='Position du chauffeur invalide.'), 400
    offer = fetch_one(
        "SELECT pickup_latitude, pickup_longitude FROM courses "
        "WHERE id=%s AND status='pending' AND driver_user_id IS NULL", (course_id,))
    if not offer:
        return jsonify(message='Course indisponible.'), 409
    if _distance_km(*point, offer['pickup_latitude'], offer['pickup_longitude']) > 15:
        return jsonify(message='Course hors de votre zone de 15 km.'), 409
    info = fetch_one('SELECT nom, prenom FROM user_info WHERE id_user=%s', (g.user_id,))
    driver_name = ' '.join(str(info.get(key) or '').strip() for key in ('prenom', 'nom')).strip() if info else None
    # Conditional UPDATE arbitrates competing drivers at the database, not in memory.
    with Database() as cursor:
        cursor.execute('SELECT available, updated_at FROM driver_presence '
                       'WHERE driver_user_id=%s FOR UPDATE', (g.user_id,))
        presence = cursor.fetchone()
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        if not presence or not presence['available'] or presence['updated_at'] < now - timedelta(seconds=30):
            return jsonify(message='Passez en ligne et activez votre position GPS.'), 409
        changed = cursor.execute("UPDATE courses SET driver_user_id=%s, driver_name=%s, status='assigned' "
                                 "WHERE id=%s AND status='pending' AND driver_user_id IS NULL",
                                 (g.user_id, driver_name, course_id))
        if changed:
            cursor.execute('UPDATE driver_presence SET available=0 WHERE driver_user_id=%s',
                           (g.user_id,))
            cursor.execute('INSERT INTO course_positions '
                           '(course_id, actor, user_id, latitude, longitude) '
                           "VALUES (%s,'driver',%s,%s,%s)",
                           (course_id, g.user_id, *point))
    if not changed:
        exists = fetch_one('SELECT id FROM courses WHERE id=%s', (course_id,))
        return jsonify(message='Course introuvable.' if not exists else 'Course déjà attribuée.'), 404 if not exists else 409
    course = _course(course_id, 'driver')
    return _snapshot(course), 200


def _update_position(course_id, role):
    point = _coordinates(request.get_json(silent=True) or {})
    if point is None:
        return jsonify(message='Coordonnées invalides.'), 400
    # Read the row under lock so a status transition cannot authorize a late update.
    with Database() as cursor:
        cursor.execute('SELECT id, user_id, driver_user_id, status FROM courses WHERE id=%s FOR UPDATE',
                       (course_id,))
        course = cursor.fetchone()
        if not course:
            return jsonify(message='Course introuvable.'), 404
        owner = course['user_id'] if role == 'client' else course['driver_user_id']
        if owner != g.user_id:
            return jsonify(message='Accès interdit à cette course.'), 403
        allowed = ('pending', 'assigned', 'arrived', 'in_transit') if role == 'client' else ('assigned', 'arrived', 'in_transit')
        if course['status'] not in allowed:
            return jsonify(message='Le suivi de cette course est terminé.'), 409
        cursor.execute('INSERT INTO course_positions '
                       '(course_id, actor, user_id, latitude, longitude) VALUES (%s,%s,%s,%s,%s) '
                       'ON DUPLICATE KEY UPDATE user_id=VALUES(user_id), latitude=VALUES(latitude), '
                       'longitude=VALUES(longitude), updated_at=CURRENT_TIMESTAMP(3)',
                       (course_id, role, g.user_id, *point))
        if role == 'driver':
            # Keep legacy tracking consumers in sync with the normalized position row.
            cursor.execute('UPDATE courses SET driver_latitude=%s, driver_longitude=%s WHERE id=%s',
                           (*point, course_id))
    return _snapshot(_course(course_id, role))


@positions_bp.put('/courses/<int:course_id>/position')
@authenticated
def client_position(course_id):
    return _update_position(course_id, 'client')


@positions_bp.put('/driver/courses/<int:course_id>/position')
@driver_authenticated
def driver_position(course_id):
    return _update_position(course_id, 'driver')


def _get_positions(course_id, role):
    course = _course(course_id, role)
    if not course:
        return jsonify(message='Course introuvable ou accès interdit.'), 404
    return _snapshot(course)


@positions_bp.get('/courses/<int:course_id>/positions')
@authenticated
def client_positions(course_id):
    return _get_positions(course_id, 'client')


@positions_bp.get('/driver/courses/<int:course_id>/positions')
@driver_authenticated
def driver_positions(course_id):
    return _get_positions(course_id, 'driver')


@positions_bp.put('/driver/courses/<int:course_id>/status')
@driver_authenticated
def change_driver_course_status(course_id):
    requested = str((request.get_json(silent=True) or {}).get('status') or '')
    predecessors = {'arrived': 'assigned', 'in_transit': 'arrived',
                    'delivered': 'in_transit'}
    previous = predecessors.get(requested)
    if not previous:
        return jsonify(message='Transition de course invalide.'), 400
    with Database() as cursor:
        changed = cursor.execute(
            'UPDATE courses SET status=%s WHERE id=%s AND driver_user_id=%s AND status=%s',
            (requested, course_id, g.user_id, previous))
    if not changed:
        return jsonify(message='Course absente ou statut déjà modifié.'), 409
    return _snapshot(_course(course_id, 'driver'))
