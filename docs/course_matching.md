# Courses client ↔ chauffeur

Ordre des migrations sur la base MariaDB partagée :
1. `001_client_api.sql` (table `courses`).
2. `002_course_positions.sql` (liaison chauffeur et positions).
3. `003_client_phone_codes.sql` (OTP client).
4. `004_driver_presence.sql` (disponibilité chauffeur).

Configurer `TAKO_CLIENT_ROLE_ID`, `TAKO_DRIVER_ROLE_ID`, `TAKO_JWT_SECRET`
dans l'auth service ; `AUTH_SERVICE_URL` et
`TAKO_API_KEY_INTER_SERVICES` dans la Gateway. L'app Flutter utilise
`TAKO_API_BASE_URL` et l'app Expo `EXPO_PUBLIC_TAKO_API_BASE_URL` ;
ces adresses pointent vers la Gateway HTTPS (sans barre finale).

Flux : POST /api/v1/courses (client) → pending ; PUT
/api/v1/driver/presence (chauffeur) → GPS et disponibilité ;
GET /api/v1/driver/courses/available → offres à 15 km max avec
présence datant de moins de 30 secondes ; POST
/api/v1/driver/courses/:id/accept → assigned par écriture conditionnelle ;
PUT /api/v1/driver/courses/:id/status → arrived, in_transit, delivered.
La position de chacun est mise à jour via PUT .../position et lue via
GET .../positions toutes les cinq secondes tant que l'écran est ouvert.

La table `courses` est la source de vérité. Le modèle `Ride` du service
transactions est distinct et ne doit pas recevoir une seconde copie des
courses sans migration et contrat d'événements transactionnels explicites.

Validation sur serveur : appliquer les migrations dans l'ordre, vérifier
les rôles existants, puis tester avec deux comptes réels sur deux appareils.
L'application chauffeur utilise la localisation au premier plan ; elle ne
publie pas sa position une fois fermée ou en arrière-plan.
