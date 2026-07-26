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
