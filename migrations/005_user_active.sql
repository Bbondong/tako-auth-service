-- Run after 003_client_phone_codes.sql.
-- Existing accounts stay active (DEFAULT 1); new clients are inserted with active=0
-- and switched to 1 only after they verify the WhatsApp code.
ALTER TABLE user ADD COLUMN IF NOT EXISTS active TINYINT(1) NOT NULL DEFAULT 1;
