-- MySQL Database Setup Script for Neutral Eats
-- Run this as root or with sufficient privileges

-- Create database user
CREATE USER IF NOT EXISTS 'neutraleats_user'@'localhost' IDENTIFIED BY 'neutraleats_pass';

-- Create database
CREATE DATABASE IF NOT EXISTS neutraleats 
    CHARACTER SET utf8mb4 
    COLLATE utf8mb4_unicode_ci;

-- Grant privileges
GRANT ALL PRIVILEGES ON neutraleats.* TO 'neutraleats_user'@'localhost';

-- Apply changes
FLUSH PRIVILEGES;

-- Confirm
SELECT 'Neutral Eats database and user created successfully' AS status;