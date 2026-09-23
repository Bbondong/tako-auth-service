# Tako Auth Service

## Description

Le **Tako Auth Service** est responsable de la gestion des utilisateurs, y compris l'enregistrement, l'authentification et la réinitialisation des mots de passe. Il assure la sécurité des accès à l'application Tako.

## Fonctionnalités

- **Enregistrement des utilisateurs** : Permet aux nouveaux utilisateurs de créer un compte.
- **Authentification des utilisateurs** : Vérifie les identifiants des utilisateurs et gère les sessions (via des tokens JWT en production).
- **Gestion des mots de passe oubliés** : Fournit un mécanisme pour réinitialiser les mots de passe.
- **Sécurité des mots de passe** : Utilise le hachage sécurisé pour stocker les mots de passe.

## Architecture

Le service est développé en Python avec Flask et Flask-SQLAlchemy, et utilise MySQL comme base de données. Il suit une architecture modulaire :

```text
auth_service/
├── app.py              # Point d'entrée principal de l'application Flask
├── requirements.txt    # Dépendances Python
└── src/
    ├── __init__.py
    ├── data.py         # Initialisation de l'objet SQLAlchemy 'db'
    ├── models/         # Définition des modèles de données (ex: User)
    │   └── user_model.py
    ├── routes/         # Définition des routes API pour chaque fonctionnalité
    │   ├── login.py
    │   ├── register.py
    │   └── forgot_password.py
    └── services/       # Logique métier et interaction avec les modèles
        └── auth_service.py
```

## Configuration

La connexion à la base de données MySQL est configurée dans `app.py`:

```python
app.config["SQLALCHEMY_DATABASE_URI"] = "mysql+mysqlconnector://user:password@db/auth_db"
```

Il est essentiel de remplacer `user`, `password`, et `db` par les informations d'identification et l'adresse de votre serveur MySQL. En production, utilisez des variables d'environnement pour ces informations sensibles.

## Installation et Exécution (Développement)

1.  **Cloner le dépôt** :
    ```bash
    git clone https://github.com/Bbondong/tako-auth-service.git
    cd tako-auth-service
    ```

2.  **Créer un environnement virtuel et installer les dépendances** :
    ```bash
    python -m venv venv
    source venv/bin/activate  # Sur Windows: .\venv\Scripts\activate
    pip install -r requirements.txt
    ```

3.  **Lancer le service** :
    ```bash
    python app.py
    ```
    Le service sera accessible sur `http://localhost:5001`.

## Endpoints API

-   `GET /` : Health check du service Auth.
-   `POST /register` : Enregistre un nouvel utilisateur.
    -   **Requête** : `{"username": "john_doe", "email": "john@example.com", "password": "secure_password"}`
-   `POST /login` : Authentifie un utilisateur.
    -   **Requête** : `{"username": "john_doe", "password": "secure_password"}`
-   `POST /forgot_password` : Initie le processus de réinitialisation de mot de passe.
    -   **Requête** : `{"email": "john@example.com"}`

## Déploiement

Pour un déploiement en production, il est recommandé d'utiliser Docker et un serveur WSGI comme Gunicorn. Un `Dockerfile` sera ajouté ultérieurement pour faciliter ce processus.

## Contribution

Les contributions sont les bienvenues. Veuillez suivre les directives de contribution et soumettre des pull requests.

## Licence

Ce projet est sous licence MIT. Voir le fichier `LICENSE` pour plus de détails.

## API client `/api/v1`

Apply `migrations/001_client_api.sql` to the existing MySQL/MariaDB database, after checking
that the `user.id_user` column has the same integer type as the migration's foreign keys.
`user.tel` must have a unique index. Configure `DB_*`, `TAKO_API_KEY`,
`TAKO_CLIENT_ROLE_ID` (the existing **client** role in `id_tpcompte`) and
`TAKO_JWT_SECRET` (a random string of at least 32 characters) on the auth service.
Do not reuse the chauffeur role. Keep the auth service private to the gateway.

The versioned API provides client register/login, `GET /me`, favorite CRUD,
course creation/list/detail, cargo type catalogue and read-only payment methods.
Existing `/register` and `/login` for chauffeurs remain separate. A courier or
admin service must update the course status, driver assignment, location and price;
new bookings stay `pending` until then. Optional cargo photos use Cloudinary and
require its environment variables. The role and the existing `user` schema must
be verified against the live database before applying the migration.

## Positions client et chauffeur (migration 002)

Apply `migrations/002_course_positions.sql` after migration 001. Set
`TAKO_DRIVER_ROLE_ID` to the **existing driver role** in `user.id_tpcompte`;
it must differ from `TAKO_CLIENT_ROLE_ID`. Database coordinates are
`longitude = x`, `latitude = y` (decimal degrees, WGS84). The initial client
position is inserted atomically with its booking. There is only one current
position per participant and booking; updates replace it and refresh
`updated_at`. This is not a GPS history table.

Driver app integration (the driver app is in a separate repository):

1. `POST /api/v1/driver/auth/login` with `identifier` and `password` returns a driver bearer token.
2. `GET /api/v1/driver/courses/available` lists pending bookings.
3. `POST /api/v1/driver/courses/{id}/accept` with JSON `{"latitude":-4.32,"longitude":15.31}` assigns that driver atomically and stores the driver's first position. A competing acceptance receives HTTP 409.
4. Every five seconds while tracking is active, `PUT /api/v1/driver/courses/{id}/position` with the **current** GPS coordinates. The response contains the latest client and driver positions. `GET /api/v1/driver/courses/{id}/positions` provides read-only recovery.

The client uses `PUT /api/v1/courses/{id}/position` at the same cadence and
reads the same two positions. If GPS is unavailable it uses
`GET /api/v1/courses/{id}/positions` to display the last recorded location.
Only the booking's client and the accepted driver may read or write its
positions. A driver acceptance requires a valid driver token; a client token
cannot accept bookings. The client app tracks while its tracking screen is
open; background tracking requires separate mobile OS permissions and a
background service.
