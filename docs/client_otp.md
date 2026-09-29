# Authentification client par SMS

Migration MariaDB à exécuter après 001_client_api.sql :

```sh
mysql -h "$DB_HOST" -u "$DB_USER" -p "$DB_NAME" < migrations/003_client_phone_codes.sql
```

Configurer `TAKO_JWT_SECRET` (au moins 32 caractères), `TAKO_CLIENT_ROLE_ID`,
`TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` et `TWILIO_FROM_NUMBER` dans
le service d'authentification. Le numéro Twilio doit pouvoir envoyer vers le
pays du client. Ne jamais placer ces secrets dans Flutter ni dans Git.

Le client appelle la Gateway :
- `POST /api/v1/auth/otp/request` avec `{"tel":"+243..." }` : réponse 202.
- `POST /api/v1/auth/otp/verify` avec `{"tel":"+243...","code":"123456"}`
  et, pour un nouveau compte, `nom` et `prenom` : jeton client.

Un code dure cinq minutes, au plus cinq essais, et une nouvelle demande est
bloquée pendant une minute. Aucun jeton n'est émis par la demande de code.
La colonne `user.password` héritée reçoit un secret aléatoire inaccessible
au client ; les routes historiques des chauffeurs restent en place. Les anciennes routes
client `/api/v1/auth/login` et `/api/v1/auth/register` renvoient 410 :
déployer l'app client compatible OTP en coordination avec le serveur.

Avant déploiement, vérifier l'unicité de `user.tel` sur la base réelle.
La migration ne modifie pas cette table héritée.
