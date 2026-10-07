-- Run after 005_user_active.sql. One user can own many favorite locations (1-N).
-- user_id is INT to match user.id_user exactly (001_client_api.sql used BIGINT).
CREATE TABLE IF NOT EXISTS favorite_locations (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  title VARCHAR(100) NOT NULL,
  address VARCHAR(500) NOT NULL,
  latitude DECIMAL(10,7) NOT NULL,
  longitude DECIMAL(10,7) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_favorites_user (user_id),
  CONSTRAINT fk_favorites_user FOREIGN KEY (user_id) REFERENCES user(id_user) ON DELETE CASCADE
) ENGINE=InnoDB;
