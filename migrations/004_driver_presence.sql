-- Run after 001_client_api.sql and 002_course_positions.sql.
CREATE TABLE IF NOT EXISTS driver_presence (
  driver_user_id BIGINT NOT NULL PRIMARY KEY,
  latitude DECIMAL(10,7) NOT NULL,
  longitude DECIMAL(10,7) NOT NULL,
  available BOOLEAN NOT NULL DEFAULT FALSE,
  updated_at TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
    ON UPDATE CURRENT_TIMESTAMP(3),
  INDEX idx_driver_presence_available (available, updated_at),
  CONSTRAINT fk_driver_presence_user FOREIGN KEY (driver_user_id)
    REFERENCES user(id_user) ON DELETE CASCADE
) ENGINE=InnoDB;
