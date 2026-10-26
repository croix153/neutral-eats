-- Neutral Eats Database Schema (MySQL)
-- Run this in MySQL to create the database and tables

CREATE DATABASE IF NOT EXISTS neutraleats 
    CHARACTER SET utf8mb4 
    COLLATE utf8mb4_unicode_ci;

USE neutraleats;

-- Main venues table
CREATE TABLE venues (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    lat DECIMAL(10, 8) NOT NULL,
    lng DECIMAL(11, 8) NOT NULL,
    type ENUM('restaurant', 'cafe', 'bar', 'pub', 'shop') NOT NULL,
    cuisine VARCHAR(100),
    brand VARCHAR(100),
    source ENUM('overture', 'osm') NOT NULL,
    source_id VARCHAR(64),
    rating DECIMAL(2, 1),
    price_level TINYINT,
    address VARCHAR(255),
    city VARCHAR(100),
    state VARCHAR(50),
    zip VARCHAR(20),
    phone VARCHAR(50),
    website VARCHAR(255),
    hours JSON,
    photos JSON,
    last_updated INT UNSIGNED NOT NULL,
    first_seen INT UNSIGNED NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    check_count INT UNSIGNED DEFAULT 1,
    grid_cell VARCHAR(20),
    INDEX idx_location (lat, lng),
    INDEX idx_type (type),
    INDEX idx_grid (grid_cell),
    INDEX idx_active (is_active),
    INDEX idx_source (source),
    INDEX idx_updated (last_updated),
    FULLTEXT idx_search (name, cuisine, brand, address)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Grid cells for spatial indexing
CREATE TABLE grid_cells (
    cell_key VARCHAR(20) PRIMARY KEY,
    lat_min DECIMAL(10, 8) NOT NULL,
    lat_max DECIMAL(10, 8) NOT NULL,
    lng_min DECIMAL(11, 8) NOT NULL,
    lng_max DECIMAL(11, 8) NOT NULL,
    venue_count INT UNSIGNED DEFAULT 0,
    last_fetched INT UNSIGNED,
    next_fetch INT UNSIGNED,
    fetch_count INT UNSIGNED DEFAULT 0,
    INDEX idx_next_fetch (next_fetch)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Sync log for tracking data refreshes
CREATE TABLE sync_log (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    source ENUM('overture', 'overpass', 'manual') NOT NULL,
    grid_cell VARCHAR(20),
    venues_added INT UNSIGNED DEFAULT 0,
    venues_updated INT UNSIGNED DEFAULT 0,
    venues_removed INT UNSIGNED DEFAULT 0,
    started_at INT UNSIGNED NOT NULL,
    completed_at INT UNSIGNED,
    status ENUM('running', 'success', 'error'),
    error_message TEXT,
    INDEX idx_started (started_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Pending updates (for incremental refreshes)
CREATE TABLE pending_updates (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    venue_id VARCHAR(64) NOT NULL,
    update_type ENUM('refresh', 'verify', 'remove') NOT NULL,
    priority TINYINT DEFAULT 0,
    created_at INT UNSIGNED NOT NULL,
    processed_at INT UNSIGNED,
    FOREIGN KEY (venue_id) REFERENCES venues(id) ON DELETE CASCADE,
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;