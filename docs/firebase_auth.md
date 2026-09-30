# Firebase téléphone → JWT Tako

Le client Flutter valide le SMS auprès de Firebase, puis envoie son ID token à
`POST /api/v1/auth/firebase-login`. Le serveur vérifie signature, projet, expiration
et révocation via Firebase Admin (`check_revoked=True`). Il exige le fournisseur
`phone` et lit le téléphone dans les claims vérifiés, jamais dans le JSON client.

## Configuration serveur

1. Installer `pip install -r requirements.txt` (Python 3.9+).
2. Dans le même projet Firebase que Flutter : Paramètres du projet → Comptes de
   service → Générer une nouvelle clé privée.
3. Placer `firebase-service-account.json` dans un secret monté côté serveur, par
   exemple `/run/secrets/firebase-service-account.json`. Ne pas le mettre dans Git,
   l'image Docker ou l'application Flutter.
4. Définir `FIREBASE_CREDENTIALS_PATH` avec ce chemin. Le compte doit pouvoir lire
   les utilisateurs Firebase Authentication pour contrôler les révocations.
5. Conserver `TAKO_JWT_SECRET` (32 caractères minimum), `TAKO_CLIENT_ROLE_ID`
   correspondant au rôle client existant, et les paramètres MySQL/MariaDB.
6. Redémarrer le service Flask. La clé manquante ou invalide ne bloque pas les
   anciennes routes ; la nouvelle route renvoie HTTP 503.

Ne pas définir `FIREBASE_AUTH_EMULATOR_HOST` sur le serveur de production.
Le SDK traite cette variable comme une activation du mode émulateur.

## Schéma existant

La route réutilise `user.tel`, `user.id_tpcompte` et `client_profiles` (migration
`001_client_api.sql`). Aucun champ Firebase UID ni nouvelle table ne sont requis.
`user.tel` doit être unique et les numéros clients stockés au format E.164
(`+243…`). Vérifier et nettoyer les doublons/anciens formats avant activation.
Un compte avec un autre rôle est refusé (403), sans modification de ses données.
La colonne legacy `password NOT NULL` reçoit un secret aléatoire inutilisable par
le client. Les mots de passe des chauffeurs ne changent pas.

## Contrat HTTP

```json
{"id_token":"<Firebase ID token>","nom":"Mukulu","prenom":"Beny"}
```

`nom`/`prenom` sont nécessaires uniquement si le compte/profil client est absent.
Réponse 200 : `access_token` (JWT Tako) et `user` (`id`, `tel`, `nom`, `prenom`).
Le profil existant n'est pas remplacé par les noms envoyés à la connexion.

| HTTP | Cas |
| --- | --- |
| 400 | JSON, jeton manquant ou noms invalides |
| 401 | Jeton invalide, expiré, révoqué, compte Firebase désactivé ou fournisseur différent |
| 403 | Numéro déjà associé à un autre type de compte Tako |
| 422 | `code: profile_required` ; compléter les noms et refaire l'échange du même jeton |
| 503 | Identifiants Admin manquants, Firebase/SQL indisponible ou JWT mal configuré |

La Gateway relaie déjà `/api/v1/*` à ce service. Conserver ses variables
`AUTH_SERVICE_URL`, `TAKO_API_KEY_INTER_SERVICES` et le `TAKO_API_KEY` du service.
Les anciens endpoints OTP/Twilio et chauffeur sont conservés pour compatibilité.

## Vérification

`python -m unittest discover -s tests -v` : tests HTTP Flask avec frontières
Firebase/MySQL simulées. Aucun test n'envoie de vrai SMS ou ne modifie MariaDB.
Après configuration, tester un numéro de test Firebase, un client existant, puis
un SMS réel sur appareil. Les tests locaux ne valident pas ces services externes.
