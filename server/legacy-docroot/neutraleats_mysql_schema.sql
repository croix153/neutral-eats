-- Neutral Eats Database Schema (MySQL version)

-- Main venues table
CREATE TABLE IF NOT EXISTS venues (
    id VARCHAR(255) PRIMARY KEY,
    name VARCHAR(500) NOT NULL,
    lat DECIMAL(10, 8) NOT NULL,
    lng DECIMAL(11, 8) NOT NULL,
    type VARCHAR(100) NOT NULL,
    cuisine VARCHAR(200),
    brand VARCHAR(200),
    source VARCHAR(50) NOT NULL,
    source_id VARCHAR(255),
    rating DECIMAL(3, 2),
    price_level TINYINT,
    address VARCHAR(500),
    city VARCHAR(200),
    state VARCHAR(100),
    zip VARCHAR(20),
    phone VARCHAR(50),
    website VARCHAR(500),
    hours TEXT,
    photos TEXT,
    last_updated INT NOT NULL,
    first_seen INT NOT NULL,
    is_active TINYINT DEFAULT 1,
    check_count INT DEFAULT 1,
    grid_cell VARCHAR(100),
    FULLTEXT INDEX ft_name (name),
    FULLTEXT INDEX ft_cuisine (cuisine),
    INDEX idx_lat (lat),
    INDEX idx_lng (lng),
    INDEX idx_type (type),
    INDEX idx_grid (grid_cell),
    INDEX idx_active (is_active),
    INDEX idx_source (source),
    INDEX idx_updated (last_updated)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Grid cells for spatial indexing
CREATE TABLE IF NOT EXISTS grid_cells (
    cell_key VARCHAR(100) PRIMARY KEY,
    lat_min DECIMAL(10, 8) NOT NULL,
    lat_max DECIMAL(10, 8) NOT NULL,
    lng_min DECIMAL(11, 8) NOT NULL,
    lng_max DECIMAL(11, 8) NOT NULL,
    venue_count INT DEFAULT 0,
    last_fetched INT,
    next_fetch INT,
    fetch_count INT DEFAULT 0,
    INDEX idx_next_fetch (next_fetch)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Sync log for tracking data refreshes
CREATE TABLE IF NOT EXISTS sync_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    source VARCHAR(100) NOT NULL,
    grid_cell VARCHAR(100),
    venues_added INT DEFAULT 0,
    venues_updated INT DEFAULT 0,
    venues_removed INT DEFAULT 0,
    started_at INT NOT NULL,
    completed_at INT,
    status VARCHAR(50),
    error_message TEXT,
    INDEX idx_started (started_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Pending updates (for incremental refreshes)
CREATE TABLE IF NOT EXISTS pending_updates (
    id INT AUTO_INCREMENT PRIMARY KEY,
    venue_id VARCHAR(255) NOT NULL,
    update_type VARCHAR(50) NOT NULL,
    priority INT DEFAULT 0,
    created_at INT NOT NULL,
    processed_at INT,
    INDEX idx_venue (venue_id),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
