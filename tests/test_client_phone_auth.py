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
                elif sql.startswith('SELECT u.id_user'):
                    self.result = state.users.get(params[0])
                elif sql.startswith('INSERT INTO user '):
                    self.lastrowid = 10
                    state.users[params[0]] = {'id_user': 10, 'nom': None, 'prenom': None}
                elif sql.startswith('INSERT INTO client_profiles'):
                    user_id, nom, prenom = params
                    state.users[next(iter(state.users))].update(nom=nom, prenom=prenom)
                else:
                    raise AssertionError(sql)
            def fetchone(self): return self.result
        class Database:
            def __enter__(self): return Cursor()
            def __exit__(self, *args): return False
        self.module.Database = Database

    def test_new_client_requires_code_then_profile(self):
        tel = '+243812345678'
        self.payload = {'tel': tel}
        result, status = self.module.request_code()
        self.assertEqual(status, 202)
        self.assertEqual(self.sms[0][0], tel)
        self.payload['code'] = '000000'
        result, status = self.module.verify_code()
        self.assertEqual(status, 401)
        self.payload['code'] = self.sms[0][1]
        result, status = self.module.verify_code()
        self.assertEqual(status, 422)
        self.payload.update(nom='K', prenom='B')
        result = self.module.verify_code()
        self.assertEqual(result['access_token'], 'token:10')
        self.assertEqual(result['user']['nom'], 'K')
        self.assertNotIn(tel, self.codes)
        result, status = self.module.verify_code()
        self.assertEqual(status, 401)

    def test_cooldown_and_phone_validation(self):
        self.payload = {'tel': '12345'}
        result, status = self.module.request_code()
        self.assertEqual(status, 400)
        self.payload = {'tel': '+243812345678'}
        self.module.request_code()
        result, status = self.module.request_code()
        self.assertEqual(status, 429)
        self.assertEqual(len(self.sms), 1)


if __name__ == '__main__':
    unittest.main()
