"""Real Flask HTTP tests; Firebase/network and MySQL boundaries are mocked."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import jwt
from firebase_admin import auth
from flask import Flask
from pymysql import OperationalError, IntegrityError

from src.routes import firebase_auth as route
from src.services.firebase_service import init_firebase


class FirebaseLoginTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            'TAKO_CLIENT_ROLE_ID': '2', 'TAKO_JWT_SECRET': 's' * 40}, clear=False)
        self.env.start()
        self.app = Flask(__name__)
        self.app.register_blueprint(route.firebase_bp)
        self.firebase_app = object()
        self.app.extensions['tako_firebase'] = self.firebase_app
        self.client = self.app.test_client()
        self.tel = '+243812345678'
        self.claims = {'uid': 'firebase-uid', 'phone_number': self.tel,
                       'firebase': {'sign_in_provider': 'phone'}}
        self.verifier = patch.object(route.auth, 'verify_id_token', return_value=self.claims)
        self.verify = self.verifier.start()
        self.users = {}
        self.inserts = []
        state = self

        class Cursor:
            lastrowid = 9
            result = None

            def execute(self, sql, params):
                if sql.startswith('SELECT u.id_user'):
                    self.result = state.users.get(params[0])
                elif sql.startswith('INSERT INTO user '):
                    state.inserts.append(params)
                    state.users[params[0]] = dict(id_user=9, id_tpcompte=params[2],
                                                nom=None, prenom=None)
                elif sql.startswith('INSERT INTO client_profiles'):
                    state.users[state.tel].update(nom=params[1], prenom=params[2])
                else:
                    raise AssertionError(sql)

            def fetchone(self):
                return self.result

        class Database:
            def __enter__(self):
                return Cursor()

            def __exit__(self, *args):
                return False

        self.database = patch.object(route, 'Database', Database)
        self.database.start()

    def tearDown(self):
        self.database.stop()
        self.verifier.stop()
        self.env.stop()

    def post(self, **values):
        return self.client.post('/api/v1/auth/firebase-login',
                                json={'id_token': 'firebase-token', **values})

    def test_existing_client_receives_internal_jwt_without_profile_overwrite(self):
        self.users[self.tel] = dict(id_user=4, id_tpcompte=2, nom='Ancien', prenom='Client')
        response = self.post(nom='Autre', prenom='Nom')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['user']['nom'], 'Ancien')
        claims = jwt.decode(response.json['access_token'], 's' * 40, algorithms=['HS256'])
        self.assertEqual((claims['sub'], claims['role']), ('4', 'client'))
        self.verify.assert_called_once_with('firebase-token', app=self.firebase_app, check_revoked=True)
        self.assertFalse(self.inserts)

    def test_new_client_needs_profile_then_can_retry_same_firebase_session(self):
        response = self.post()
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json['code'], 'profile_required')
        self.assertFalse(self.users)
        response = self.post(nom=' Mukulu ', prenom=' Beny ')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['user']['tel'], self.tel)
        self.assertEqual(response.json['user']['nom'], 'Mukulu')
        self.assertNotEqual(self.inserts[0][1], 'firebase-token')
        self.assertEqual(self.inserts[0][2], 2)
        self.assertEqual(self.post().status_code, 200)
        self.assertEqual(len(self.inserts), 1)

    def test_existing_user_without_client_profile_is_completed(self):
        self.users[self.tel] = dict(id_user=8, id_tpcompte=2, nom=None, prenom=None)
        self.assertEqual(self.post().status_code, 422)
        response = self.post(nom='K', prenom='B')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['user']['id'], 8)
        self.assertFalse(self.inserts)

    def test_driver_account_is_never_converted(self):
        self.users[self.tel] = dict(id_user=5, id_tpcompte=5, nom=None, prenom=None)
        self.assertEqual(self.post(nom='K', prenom='B').status_code, 403)
        self.assertEqual(self.users[self.tel]['id_tpcompte'], 5)
        self.assertFalse(self.inserts)

    def test_invalid_expired_revoked_disabled_tokens_are_rejected_before_sql(self):
        errors = [auth.InvalidIdTokenError('invalid'), auth.ExpiredIdTokenError('expired', None),
                  auth.RevokedIdTokenError('revoked'), auth.UserDisabledError('disabled')]
        for error in errors:
            with self.subTest(error=type(error).__name__):
                self.verify.side_effect = error
                self.assertEqual(self.post().status_code, 401)
                self.assertFalse(self.users)

    def test_unverified_phone_and_other_providers_are_rejected(self):
        for claims in ({'firebase': {'sign_in_provider': 'phone'}},
                       {'phone_number': self.tel, 'firebase': {'sign_in_provider': 'password'}},
                       {'phone_number': '123', 'firebase': {'sign_in_provider': 'phone'}}):
            self.verify.return_value = claims
            self.assertEqual(self.post().status_code, 401)
        self.assertFalse(self.users)

    def test_malformed_input_never_reaches_firebase(self):
        for payload in ([], {}, {'id_token': 123}, {'id_token': 'ok', 'nom': {}},
                        {'id_token': 'ok', 'prenom': 'x' * 101}):
            response = self.client.post('/api/v1/auth/firebase-login', json=payload)
            self.assertEqual(response.status_code, 400)
        self.verify.assert_not_called()

    def test_missing_admin_configuration_keeps_other_routes_available(self):
        self.app.extensions['tako_firebase'] = None
        self.assertEqual(self.post().status_code, 503)
        self.verify.assert_not_called()

    def test_unavailable_certificates_database_and_jwt_configuration(self):
        self.verify.side_effect = auth.CertificateFetchError('offline', None)
        self.assertEqual(self.post().status_code, 503)
        self.verify.side_effect = None
        with patch.object(route, 'Database', side_effect=OperationalError(2003, 'offline')):
            self.assertEqual(self.post().status_code, 503)
        with patch.dict(os.environ, {'TAKO_JWT_SECRET': ''}):
            self.assertEqual(self.post(nom='K', prenom='B').status_code, 503)
            self.assertFalse(self.inserts)

    def test_concurrent_duplicate_creation_retries_after_rollback(self):
        with patch.object(route, '_client_session', side_effect=[
                IntegrityError(1062, 'duplicate'), ({'access_token': 'existing'}, 200)]) as session:
            self.assertEqual(self.post(nom='K', prenom='B').status_code, 200)
            self.assertEqual(session.call_count, 2)

    def test_waf_leaves_token_to_firebase_but_still_filters_names(self):
        from securite.securite import init_security
        init_security(self.app)
        response = self.client.post('/api/v1/auth/firebase-login', json={
            'id_token': 'opaque--signature', 'nom': 'K', 'prenom': 'B'})
        self.assertEqual(response.status_code, 200)
        response = self.post(nom='DROP TABLE user', prenom='B')
        self.assertEqual(response.status_code, 400)


class FirebaseInitializationTests(unittest.TestCase):
    def test_missing_and_invalid_credentials_do_not_crash_flask(self):
        for path in ('', '/nonexistent/firebase-service-account.json'):
            app = Flask(__name__)
            with patch.dict(os.environ, {'FIREBASE_CREDENTIALS_PATH': path}):
                init_firebase(app)
                self.assertIsNone(app.extensions['tako_firebase'])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'firebase-service-account.json'
            path.write_text('{}')
            with patch.dict(os.environ, {'FIREBASE_CREDENTIALS_PATH': str(path)}):
                init_firebase(app)
                self.assertIsNone(app.extensions['tako_firebase'])


if __name__ == '__main__':
    unittest.main()
