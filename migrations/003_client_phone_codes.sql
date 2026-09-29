-- Apply after 001_client_api.sql. One outstanding challenge per E.164 phone number.
CREATE TABLE IF NOT EXISTS client_phone_codes (
  tel VARCHAR(25) NOT NULL PRIMARY KEY,
  code_hash CHAR(64) NOT NULL,
  expires_at DATETIME(6) NOT NULL,
  sent_at DATETIME(6) NOT NULL,
  attempts TINYINT UNSIGNED NOT NULL DEFAULT 0
) ENGINE=InnoDB;
