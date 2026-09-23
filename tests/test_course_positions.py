"""Dependency-free behavioral checks for assignment and position authorization.

Uses a small in-memory SQL adapter because the CI environment need not run MariaDB.
The deployment migration and real database must still be tested separately.
"""
import importlib
from pathlib import Path
import sys
import types
import unittest
from datetime import datetime


class Cursor:
    def __init__(self, state):
        self.state = state
        self.result = None

    def execute(self, sql, params):
        course = self.state['course']
        if sql.startswith('UPDATE courses SET driver_user_id='):
            assert "WHERE id=%s AND status='pending' AND driver_user_id IS NULL" in sql
            driver_id, name, course_id = params
            if course_id != course['id'] or course['status'] != 'pending' or course['driver_user_id'] is not None:
                return 0
            course.update(driver_user_id=driver_id, driver_name=name, status='assigned')
            return 1
        if sql.startswith('SELECT id, user_id, driver_user_id, status FROM courses'):
            self.result = course if params[0] == course['id'] else None
            return 1 if self.result else 0
        if sql.startswith('INSERT INTO course_positions'):
            if len(params) == 4:
                course_id, driver_id, latitude, longitude = params
                self.state['positions']['driver'] = dict(course_id=course_id, user_id=driver_id,
                                                         latitude=latitude, longitude=longitude)
            else:
                course_id, actor, user_id, latitude, longitude = params
                self.state['positions'][actor] = dict(course_id=course_id, user_id=user_id,
                                                      latitude=latitude, longitude=longitude)
            return 1
        if sql.startswith('UPDATE courses SET driver_latitude='):
            course['driver_latitude'], course['driver_longitude'], _ = params
            return 1
        raise AssertionError(f'Unexpected SQL: {sql}')

    def fetchone(self):
        return self.result


class TestPositions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        flask = types.ModuleType('flask')
        flask.g = types.SimpleNamespace(user_id=None)
        flask.request = types.SimpleNamespace(get_json=lambda silent=True: {})
        flask.jsonify = lambda **values: values
        class Blueprint:
            def __init__(self, *args, **kwargs): pass
            def get(self, path): return lambda fn: fn
            def post(self, path): return lambda fn: fn
            def put(self, path): return lambda fn: fn
        flask.Blueprint = Blueprint
        sys.modules['flask'] = flask
        jwt = types.ModuleType('jwt')
        jwt.InvalidTokenError = type('InvalidTokenError', (Exception,), {})
        sys.modules['jwt'] = jwt
        data = types.ModuleType('src.data')
        sys.modules['src.data'] = data
        api = types.ModuleType('src.routes.client_api')
        api._secret = lambda: 'test-secret'
        api._role = lambda: 2
        api.authenticated = lambda fn: fn
        sys.modules['src.routes.client_api'] = api
        service = types.ModuleType('src.services.auth_service')
        service.login_user = lambda identifier, password: (None, 'Invalid')
        sys.modules['src.services.auth_service'] = service
        data.Database = lambda: None
        data.fetch_one = lambda *args: None
        data.fetch_all = lambda *args: []
        cls.module = importlib.import_module('src.routes.course_positions')
        cls.flask = flask

    def setUp(self):
        self.state = {'course': {'id': 4, 'user_id': 10, 'driver_user_id': None,
                                 'driver_name': None, 'vehicle': None, 'price': None,
                                 'status': 'pending'}, 'positions': {}}
        class Database:
            def __enter__(_): return Cursor(self.state)
            def __exit__(_, *exc): return False
        self.module.Database = Database
        def fetch_one(sql, params):
            if 'FROM user_info' in sql: return {'prenom': 'Jean', 'nom': 'Test'}
            if 'SELECT id FROM courses' in sql:
                return {'id': 4} if params[0] == 4 else None
            if 'FROM courses' in sql:
                course = self.state['course']
                account = course['user_id'] if 'user_id=%s' in sql and 'driver_user_id=%s' not in sql else course['driver_user_id']
                return course if params == (4, account) and account is not None else None
            return None
        self.module.fetch_one = fetch_one
        self.module.fetch_all = lambda sql, params: [dict(actor=role, updated_at=datetime.now(), **position)
                                                       for role, position in self.state['positions'].items()]
        self.flask.request.get_json = lambda silent=True: {'latitude': -4.32, 'longitude': 15.31}

    def test_first_driver_wins_and_second_cannot_overwrite(self):
        self.flask.g.user_id = 7
        response, status = self.module.accept_course.__wrapped__(4)
        self.assertEqual(status, 200)
        self.assertEqual(response['positions']['driver']['latitude'], -4.32)
        self.assertEqual(self.state['course']['driver_user_id'], 7)
        self.flask.g.user_id = 8
        response, status = self.module.accept_course.__wrapped__(4)
        self.assertEqual(status, 409)
        self.assertEqual(self.state['course']['driver_user_id'], 7)
        self.assertEqual(self.state['positions']['driver']['user_id'], 7)

    def test_unassigned_driver_cannot_read_or_update_positions(self):
        self.flask.g.user_id = 7
        self.module.accept_course.__wrapped__(4)
        self.flask.g.user_id = 8
        response, status = self.module._update_position(4, 'driver')
        self.assertEqual(status, 403)
        response, status = self.module._get_positions(4, 'driver')
        self.assertEqual(status, 404)
        self.assertEqual(self.state['positions']['driver']['user_id'], 7)

    def test_other_client_cannot_overwrite_position(self):
        self.flask.g.user_id = 11
        response, status = self.module._update_position(4, 'client')
        self.assertEqual(status, 403)
        self.assertNotIn('client', self.state['positions'])

    def test_invalid_coordinates_rejected(self):
        self.assertIsNone(self.module._coordinates({'latitude': float('nan'), 'longitude': 0}))
        self.assertIsNone(self.module._coordinates({'latitude': -4, 'longitude': 181}))
        self.assertIsNone(self.module._coordinates({'latitude': None, 'longitude': 0}))


if __name__ == '__main__':
    unittest.main()
