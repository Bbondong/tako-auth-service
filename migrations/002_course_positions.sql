-- Run after 001_client_api.sql. In this schema x = longitude, y = latitude.
-- Run once during deployment (MariaDB supports IF NOT EXISTS on ADD COLUMN).
ALTER TABLE courses ADD COLUMN IF NOT EXISTS driver_user_id BIGINT NULL;
CREATE INDEX IF NOT EXISTS idx_courses_driver ON courses (driver_user_id, status);

CREATE TABLE IF NOT EXISTS course_positions (
  course_id BIGINT NOT NULL,
  actor ENUM('client', 'driver') NOT NULL,
  user_id BIGINT NOT NULL,
  longitude DECIMAL(10,7) NOT NULL COMMENT 'x',
  latitude DECIMAL(10,7) NOT NULL COMMENT 'y',
  updated_at TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
    ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (course_id, actor),
  CONSTRAINT fk_course_positions_course FOREIGN KEY (course_id)
    REFERENCES courses(id) ON DELETE CASCADE
);

-- Preserve initial coordinates for bookings created before this migration.
INSERT IGNORE INTO course_positions (course_id, actor, user_id, longitude, latitude)
SELECT id, 'client', user_id, pickup_longitude, pickup_latitude FROM courses;
