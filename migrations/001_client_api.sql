-- Configure TAKO_CLIENT_ROLE_ID to the existing client id_tpcompte value.
-- Ensure user.tel has a unique index before enabling registration.
CREATE TABLE IF NOT EXISTS client_profiles (
  user_id BIGINT NOT NULL PRIMARY KEY,
  nom VARCHAR(100) NOT NULL, prenom VARCHAR(100) NOT NULL,
  CONSTRAINT fk_client_profile_user FOREIGN KEY (user_id) REFERENCES user(id_user) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS favorite_locations (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  user_id BIGINT NOT NULL, title VARCHAR(100) NOT NULL,
  address VARCHAR(500) NOT NULL, latitude DECIMAL(10,7) NOT NULL,
  longitude DECIMAL(10,7) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_favorites_user (user_id),
  CONSTRAINT fk_favorites_user FOREIGN KEY (user_id) REFERENCES user(id_user) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS cargo_types (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  label VARCHAR(100) NOT NULL UNIQUE, active BOOLEAN NOT NULL DEFAULT TRUE,
  sort_order INT NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS courses (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY, user_id BIGINT NOT NULL,
  pickup VARCHAR(500) NOT NULL, dropoff VARCHAR(500) NOT NULL,
  pickup_latitude DECIMAL(10,7) NOT NULL, pickup_longitude DECIMAL(10,7) NOT NULL,
  destination_latitude DECIMAL(10,7) NOT NULL, destination_longitude DECIMAL(10,7) NOT NULL,
  cargo_type VARCHAR(100) NOT NULL, weight DECIMAL(10,2) NOT NULL,
  description TEXT NULL,
  length_cm DECIMAL(10,2) NULL, width_cm DECIMAL(10,2) NULL,
  height_cm DECIMAL(10,2) NULL, is_fragile BOOLEAN NOT NULL DEFAULT FALSE,
  is_express BOOLEAN NOT NULL DEFAULT FALSE, photo_url VARCHAR(500) NULL,
  price DECIMAL(12,2) NULL, status VARCHAR(30) NOT NULL DEFAULT 'pending',
  driver_name VARCHAR(200) NULL, vehicle VARCHAR(200) NULL,
  driver_latitude DECIMAL(10,7) NULL, driver_longitude DECIMAL(10,7) NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_courses_user (user_id, created_at),
  CONSTRAINT fk_courses_user FOREIGN KEY (user_id) REFERENCES user(id_user) ON DELETE CASCADE
);

-- Reference catalogue (not user test data); edit labels and order as the business defines them.
INSERT IGNORE INTO cargo_types (label, sort_order) VALUES
 ('Colis', 10), ('Documents', 20), ('Meubles', 30), ('Électronique', 40),
 ('Alimentaire', 50), ('Matériaux', 60), ('Vêtements', 70), ('Autre', 80);
CREATE TABLE IF NOT EXISTS payment_methods (
 id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY, user_id BIGINT NOT NULL,
 title VARCHAR(100) NOT NULL, details VARCHAR(200) NOT NULL,
 INDEX idx_payment_methods_user (user_id),
 CONSTRAINT fk_payment_methods_user FOREIGN KEY (user_id) REFERENCES user(id_user) ON DELETE CASCADE
);
