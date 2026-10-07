"""Behavioral checks for SMS verification without an external SMS or SQL server."""
import importlib
from pathlib import Path
import sys
import types
import unittest
from datetime import datetime


class TestPhoneAuth(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        flask = types.ModuleType('flask')
        flask.request = types.SimpleNamespace(get_json=lambda silent=True: {})
        flask.jsonify = lambda **values: values
        class Blueprint:
            def __init__(self, *args, **kwargs): pass
            def post(self, path): return lambda fn: fn
        flask.Blueprint = Blueprint
        sys.modules['flask'] = flask
        werkzeug = types.ModuleType('werkzeug')
        security = types.ModuleType('werkzeug.security')
        security.generate_password_hash = lambda value: 'unusable:' + value
        werkzeug.security = security
        sys.modules['werkzeug'] = werkzeug
        sys.modules['werkzeug.security'] = security
        data = types.ModuleType('src.data')
        data.Database = lambda: None
        sys.modules['src.data'] = data
        api = types.ModuleType('src.routes.client_api')
        api._secret = lambda: 'test-secret-with-more-than-32-characters'
        api._role = lambda: 2
        api._token = lambda user_id: 'token:' + str(user_id)
        sys.modules['src.routes.client_api'] = api
        cls.module = importlib.import_module('src.routes.client_phone_auth')
        cls.flask = flask

    def setUp(self):
        self.codes = {}
        self.users = {}
        self.sms = []
        self.payload = {}
        self.flask.request.get_json = lambda silent=True: self.payload
        self.module._send_sms = lambda tel, code: self.sms.append((tel, code))
        state = self
        class Cursor:
            result = None
            lastrowid = 0
            def execute(self, sql, params):
                if sql.startswith('SELECT sent_at'):
                    row = state.codes.get(params[0])
                    self.result = {'sent_at': row['sent_at']} if row else None
                elif sql.startswith('SELECT code_hash'):
                    self.result = state.codes.get(params[0])
                elif sql.startswith('INSERT INTO client_phone_codes'):
                    tel, code_hash, expires_at, sent_at = params
                    state.codes[tel] = dict(code_hash=code_hash, expires_at=expires_at,
                                            sent_at=sent_at, attempts=0)
                elif sql.startswith('UPDATE client_phone_codes SET attempts'):
                    state.codes[params[0]]['attempts'] += 1
                elif sql.startswith('DELETE FROM client_phone_codes'):
                    state.codes.pop(params[0], None)
                elif sql.startswith('SELECT id_user, active'):
                    u = state.users.get(params[0])
                    self.result = {'id_user': u['id_user'], 'active': u['active']} if u else None
                elif sql.startswith('SELECT id_user FROM user'):
                    u = state.users.get(params[0])
                    self.result = {'id_user': u['id_user']} if u else None
                elif sql.startswith('SELECT u.id_user'):
                    self.result = state.users.get(params[0])
                elif sql.startswith('INSERT INTO user '):
                    self.lastrowid = 10
                    state.inserted_role = params[2]
                    state.users[params[0]] = {'id_user': 10, 'nom': None, 'prenom': None,
                                              'profil': None, 'active': 0}
                elif sql.startswith('INSERT INTO user_info'):
                    nom, postnom, prenom, sexe, adresse, matricul, profil, permis, user_id = params
                    state.driver_fields = (postnom, sexe, adresse, matricul, permis)
                    state.users[next(iter(state.users))].update(nom=nom, prenom=prenom)
                elif sql.startswith('UPDATE user SET active=1'):
                    for u in state.users.values():
                        if u['id_user'] == params[0]:
                            u['active'] = 1
                else:
                    raise AssertionError(sql)
            def fetchone(self): return self.result
        class Database:
            def __enter__(self): return Cursor()
            def __exit__(self, *args): return False
        self.module.Database = Database

    def test_register_inactive_until_code_verified(self):
        tel = '+243812345678'
        self.payload = {'tel': tel, 'nom': 'K', 'prenom': 'B'}
        result, status = self.module.register()
        self.assertEqual(status, 202)
        self.assertEqual(self.sms[0][0], tel)
        self.assertRegex(self.sms[0][1], r'^[0-9]{6}$')
        self.assertEqual(self.users[tel]['active'], 0)
        self.assertEqual(self.inserted_role, 2)
        self.assertEqual(self.driver_fields, (None, 'M', 'client-10', 'client-10', 'client-10'))
        self.payload = {'tel': tel, 'code': '000000'}
        result, status = self.module.verify_code()
        self.assertEqual(status, 401)
        self.assertEqual(self.users[tel]['active'], 0)
        self.payload['code'] = self.sms[0][1]
        result = self.module.verify_code()
        self.assertEqual(result['access_token'], 'token:10')
        self.assertEqual(result['user']['nom'], 'K')
        self.assertEqual(self.users[tel]['active'], 1)
        self.assertNotIn(tel, self.codes)
        result, status = self.module.verify_code()
        self.assertEqual(status, 401)

    def test_register_rejects_active_number_and_missing_name(self):
        tel = '+243812345678'
        self.payload = {'tel': tel}
        result, status = self.module.register()
        self.assertEqual(status, 422)
        self.users[tel] = {'id_user': 3, 'active': 1}
        self.payload = {'tel': tel, 'nom': 'K', 'prenom': 'B'}
        result, status = self.module.register()
        self.assertEqual(status, 409)
        self.assertEqual(self.sms, [])

    def test_request_unknown_number_and_cooldown(self):
        self.payload = {'tel': '12345'}
        result, status = self.module.request_code()
        self.assertEqual(status, 400)
        tel = '+243812345678'
        self.payload = {'tel': tel}
        result, status = self.module.request_code()
        self.assertEqual(status, 404)
        self.payload = {'tel': tel, 'nom': 'K', 'prenom': 'B'}
        self.module.register()
        result, status = self.module.request_code()
        self.assertEqual(status, 429)
        self.assertEqual(len(self.sms), 1)


if __name__ == '__main__':
    unittest.main()
