# Authentification client par SMS

Migration MariaDB à exécuter après 001_client_api.sql :

```sh
mysql -h "$DB_HOST" -u "$DB_USER" -p "$DB_NAME" < migrations/003_client_phone_codes.sql
```

Configurer `TAKO_JWT_SECRET` (au moins 32 caractères), `TAKO_CLIENT_ROLE_ID`,
et `WHATSAPP_API_SECRET` dans le service d'authentification. Le code est
envoyé par WhatsApp via `POST https://benbot.alwaysdata.net/send-otp`
(numéro sans `+`). Ne jamais placer ces secrets dans Flutter ni dans Git.

Migration à exécuter aussi : `migrations/005_user_active.sql` (colonne
`user.active`, `1` par défaut pour les comptes existants).

Le client appelle la Gateway :
- `POST /api/v1/auth/otp/register` avec `{"tel":"+243...","nom":"..","prenom":"..","sexe":"M"}` :
  crée le compte **inactif** et envoie le code à 6 chiffres par WhatsApp (202).
- `POST /api/v1/auth/otp/request` avec `{"tel":"+243..."}` : renvoie un code à un
  compte existant (connexion). 404 si le numéro n'est pas inscrit.
- `POST /api/v1/auth/otp/verify-code` (alias `/verify`) avec
  `{"tel":"+243...","code":"123456"}` : si le code est bon, le compte passe à
  `active=1` et le jeton client est renvoyé. Un compte inactif ne peut utiliser
  aucune route authentifiée.

Un code dure cinq minutes, au plus cinq essais, et une nouvelle demande est
bloquée pendant une minute. Aucun jeton n'est émis par la demande de code.
La colonne `user.password` héritée reçoit un secret aléatoire inaccessible
au client ; les routes historiques des chauffeurs restent en place. Les anciennes routes
client `/api/v1/auth/login` et `/api/v1/auth/register` renvoient 410 :
déployer l'app client compatible OTP en coordination avec le serveur.

Avant déploiement, vérifier l'unicité de `user.tel` sur la base réelle.
La migration ne modifie pas cette table héritée.
