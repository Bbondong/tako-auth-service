"""Firebase Admin is server-only; the private service account never enters Flutter."""
import os
from pathlib import Path

import firebase_admin
from firebase_admin import credentials


def init_firebase(app):
    app.extensions['tako_firebase'] = None
    # Mount firebase-service-account.json outside the repository/container image.
    # FIREBASE_CREDENTIALS_PATH is its absolute path on the Flask server.
    path = os.getenv('FIREBASE_CREDENTIALS_PATH', '').strip()
    if not path or not Path(path).is_file():
        app.logger.warning('Firebase non configuré : fichier de compte de service absent. '
                           'Les autres routes restent disponibles.')
        return
    try:
        try:
            firebase_app = firebase_admin.get_app('tako-auth')
        except ValueError:
            firebase_app = firebase_admin.initialize_app(
                credentials.Certificate(path), name='tako-auth')
        app.extensions['tako_firebase'] = firebase_app
    except (ValueError, OSError):
        # Do not log file contents or private keys.
        app.logger.error('Impossible de charger les identifiants Firebase Admin.')
