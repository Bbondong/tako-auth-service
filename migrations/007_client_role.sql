-- Dedicated account type for passwordless (WhatsApp OTP) clients.
-- Set TAKO_CLIENT_ROLE_ID=9 in the auth service environment.
INSERT INTO type_compte (id_tpcompte, nom_compte)
SELECT 9, 'client' FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM type_compte WHERE id_tpcompte = 9);
