-- Neutral Eats Database Schema v2.0
-- Enhanced multi-source data ingestion system
-- Run this in MySQL to upgrade from v1

-- Create database if not exists
CREATE DATABASE IF NOT EXISTS neutraleats 
    CHARACTER SET utf8mb4 
    COLLATE utf8mb4_unicode_ci;

USE neutraleats;

-- ============================================
-- VENUES TABLE (Extended)
-- ============================================
CREATE TABLE IF NOT EXISTS venues (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    lat DECIMAL(10, 8) NOT NULL,
    lng DECIMAL(11, 8) NOT NULL,
    
    -- Enhanced type system
    type ENUM('restaurant', 'cafe', 'bar', 'pub', 'shop', 
              'food_truck', 'farmers_market', 'ghost_kitchen', 
              'pop_up', 'bakery', 'deli', 'ice_cream') DEFAULT 'restaurant',
    
    cuisine VARCHAR(100),
    brand VARCHAR(100),
    
    -- Multi-source tracking
    source ENUM('overture', 'osm', 'dbpr', 'usda_farmers_market', 
                'nps', 'fl_state_parks', 'orange_county', 'miami_dade',
                'broward_county', 'hillsborough_county', 'duval_county',
                'orlando_city', 'yelp', 'google_places', 'foursquare',
                'tripadvisor', 'manual') NOT NULL,
    sub_source VARCHAR(50),
    source_id VARCHAR(128),
    source_url VARCHAR(500),
    
    -- Ratings & pricing
    rating DECIMAL(2, 1),
    rating_count INT UNSIGNED DEFAULT 0,
    price_level TINYINT,
    
    -- Location details
    address VARCHAR(255),
    city VARCHAR(100),
    state VARCHAR(50) DEFAULT 'FL',
    zip VARCHAR(20),
    county VARCHAR(50),
    
    -- Contact info
    phone VARCHAR(50),
    website VARCHAR(255),
    email VARCHAR(255),
    
    -- Hours & status
    hours JSON,
    operating_status ENUM('open', 'temporarily_closed', 'permanently_closed', 
                          'seasonal', 'coming_soon') DEFAULT 'open',
    hours_confirmed BOOLEAN DEFAULT FALSE,
    seasonal_notes VARCHAR(255),
    
    -- Government data
    license_number VARCHAR(50),
    license_type VARCHAR(50),
    license_status ENUM('active', 'inactive', 'suspended', 'expired') DEFAULT 'active',
    inspection_score DECIMAL(4, 2),
    last_inspection_date DATE,
    inspection_violations INT DEFAULT 0,
    
    -- Extended metadata (JSON for flexibility)
    metadata JSON,
    
    -- Data quality tracking
    confidence_score DECIMAL(3, 2) DEFAULT 0.50,
    data_freshness TINYINT DEFAULT 0,
    
    -- Timestamps
    last_updated INT UNSIGNED NOT NULL,
    last_verified INT UNSIGNED,
    first_seen INT UNSIGNED NOT NULL,
    
    -- Activity tracking
    is_active BOOLEAN DEFAULT TRUE,
    check_count INT UNSIGNED DEFAULT 1,
    
    -- Spatial indexing
    grid_cell VARCHAR(20),
    
    -- Indexes
    INDEX idx_location (lat, lng),
    INDEX idx_type (type),
    INDEX idx_source (source),
    INDEX idx_sub_source (sub_source),
    INDEX idx_grid (grid_cell),
    INDEX idx_active (is_active),
    INDEX idx_updated (last_updated),
    INDEX idx_verified (last_verified),
    INDEX idx_city (city),
    INDEX idx_county (county),
    INDEX idx_operating (operating_status),
    INDEX idx_license (license_number),
    FULLTEXT idx_search (name, cuisine, brand, address, city),
    SPATIAL INDEX idx_geo (geo_point)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Add geometry column for spatial queries (if MySQL 8.0+)
-- ALTER TABLE venues ADD COLUMN geo_point POINT NOT NULL SRID 4326;
-- UPDATE venues SET geo_point = ST_GeomFromText(CONCAT('POINT(', lng, ' ', lat, ')'), 4326);

-- ============================================
-- GRID CELLS (Enhanced)
-- ============================================
CREATE TABLE IF NOT EXISTS grid_cells (
    cell_key VARCHAR(20) PRIMARY KEY,
    lat_min DECIMAL(10, 8) NOT NULL,
    lat_max DECIMAL(10, 8) NOT NULL,
    lng_min DECIMAL(11, 8) NOT NULL,
    lng_max DECIMAL(11, 8) NOT NULL,
    
    -- Venue counts by source
    venue_count INT UNSIGNED DEFAULT 0,
    overture_count INT UNSIGNED DEFAULT 0,
    osm_count INT UNSIGNED DEFAULT 0,
    government_count INT UNSIGNED DEFAULT 0,
    commercial_count INT UNSIGNED DEFAULT 0,
    
    -- Sync tracking
    last_fetched INT UNSIGNED,
    next_fetch INT UNSIGNED,
    fetch_count INT UNSIGNED DEFAULT 0,
    
    -- Priority (higher = refresh more often)
    priority_score TINYINT DEFAULT 5,
    
    -- Coverage metrics
    coverage_score DECIMAL(3, 2) DEFAULT 0.00,
    
    INDEX idx_next_fetch (next_fetch),
    INDEX idx_priority (priority_score),
    INDEX idx_coverage (coverage_score)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================
-- SYNC LOG (Enhanced)
-- ============================================
CREATE TABLE IF NOT EXISTS sync_log (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    source ENUM('overture', 'overpass', 'dbpr', 'usda_farmers_market',
                'nps', 'fl_state_parks', 'orange_county', 'miami_dade',
                'broward_county', 'hillsborough_county', 'duval_county',
                'orlando_city', 'yelp', 'google_places', 'foursquare',
                'tripadvisor', 'manual', 'merge') NOT NULL,
    sub_source VARCHAR(50),
    grid_cell VARCHAR(20),
    
    -- Results
    venues_added INT UNSIGNED DEFAULT 0,
    venues_updated INT UNSIGNED DEFAULT 0,
    venues_removed INT UNSIGNED DEFAULT 0,
    venues_deduplicated INT UNSIGNED DEFAULT 0,
    
    -- Performance metrics
    api_calls INT UNSIGNED DEFAULT 0,
    bytes_downloaded INT UNSIGNED DEFAULT 0,
    processing_time_ms INT UNSIGNED,
    
    -- Status
    started_at INT UNSIGNED NOT NULL,
    completed_at INT UNSIGNED,
    status ENUM('running', 'success', 'partial', 'error') DEFAULT 'running',
    error_message TEXT,
    
    INDEX idx_started (started_at),
    INDEX idx_source (source),
    INDEX idx_status (status),
    INDEX idx_cell (grid_cell)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================
-- SOURCE METADATA
-- ============================================
CREATE TABLE IF NOT EXISTS source_metadata (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    source VARCHAR(50) NOT NULL UNIQUE,
    source_type ENUM('government', 'commercial', 'open_data', 'crowdsourced') NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    website VARCHAR(255),
    api_endpoint VARCHAR(255),
    
    -- Rate limiting
    requests_per_minute INT DEFAULT 60,
    requests_per_day INT DEFAULT 10000,
    
    -- Coverage
    coverage_area VARCHAR(100),
    
    -- Data quality
    trust_score DECIMAL(3, 2) DEFAULT 0.50,
    update_frequency_days INT DEFAULT 30,
    
    -- Status
    is_enabled BOOLEAN DEFAULT TRUE,
    last_successful_sync INT UNSIGNED,
    total_api_calls INT UNSIGNED DEFAULT 0,
    
    -- API keys (encrypted at application level)
    api_key_encrypted TEXT,
    
    INDEX idx_type (source_type),
    INDEX idx_enabled (is_enabled)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Insert default source metadata
INSERT INTO source_metadata (source, source_type, display_name, website, trust_score, update_frequency_days) VALUES
('overture', 'open_data', 'Overture Maps', 'https://overturemaps.org/', 0.85, 30),
('osm', 'crowdsourced', 'OpenStreetMap', 'https://www.openstreetmap.org/', 0.80, 14),
('dbpr', 'government', 'FL DBPR Restaurant Licenses', 'https://www.myfloridalicense.com/', 0.95, 7),
('usda_farmers_market', 'government', 'USDA Farmers Market Directory', 'https://www.ams.usda.gov/', 0.90, 30),
('nps', 'government', 'National Park Service', 'https://www.nps.gov/', 0.90, 90),
('orange_county', 'government', 'Orange County FL', 'https://www.orangecountyfl.net/', 0.90, 7),
('miami_dade', 'government', 'Miami-Dade County', 'https://www.miamidade.gov/', 0.90, 7),
('broward_county', 'government', 'Broward County', 'https://www.broward.org/', 0.90, 7),
('hillsborough_county', 'government', 'Hillsborough County', 'https://www.hillsboroughcounty.org/', 0.90, 7),
('duval_county', 'government', 'Duval County', 'https://www.coj.net/', 0.90, 7),
('orlando_city', 'government', 'City of Orlando', 'https://www.orlando.gov/', 0.90, 7),
('yelp', 'commercial', 'Yelp', 'https://www.yelp.com/', 0.75, 30),
('google_places', 'commercial', 'Google Places', 'https://developers.google.com/maps/', 0.80, 30),
('foursquare', 'commercial', 'Foursquare', 'https://foursquare.com/', 0.75, 30),
('tripadvisor', 'commercial', 'TripAdvisor', 'https://www.tripadvisor.com/', 0.70, 30)
ON DUPLICATE KEY UPDATE display_name=VALUES(display_name);

-- ============================================
-- PENDING UPDATES (Enhanced)
-- ============================================
CREATE TABLE IF NOT EXISTS pending_updates (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    venue_id VARCHAR(64) NOT NULL,
    update_type ENUM('refresh', 'verify', 'remove', 'merge', 'enrich') NOT NULL,
    priority TINYINT DEFAULT 5,
    suggested_source VARCHAR(50),
    created_at INT UNSIGNED NOT NULL,
    processed_at INT UNSIGNED,
    
    FOREIGN KEY (venue_id) REFERENCES venues(id) ON DELETE CASCADE,
    INDEX idx_created (created_at),
    INDEX idx_priority (priority),
    INDEX idx_type (update_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================
-- DUPLICATE CLUSTERS (for deduplication)
-- ============================================
CREATE TABLE IF NOT EXISTS duplicate_clusters (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    canonical_venue_id VARCHAR(64) NOT NULL,
    duplicate_venue_id VARCHAR(64) NOT NULL,
    match_score DECIMAL(4, 3) NOT NULL,
    match_reason VARCHAR(100),
    resolved_at INT UNSIGNED,
    resolution ENUM('merged', 'rejected', 'pending') DEFAULT 'pending',
    
    FOREIGN KEY (canonical_venue_id) REFERENCES venues(id) ON DELETE CASCADE,
    FOREIGN KEY (duplicate_venue_id) REFERENCES venues(id) ON DELETE CASCADE,
    UNIQUE KEY unique_pair (canonical_venue_id, duplicate_venue_id),
    INDEX idx_score (match_score),
    INDEX idx_resolution (resolution)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================
-- API CACHE (for rate limiting)
-- ============================================
CREATE TABLE IF NOT EXISTS api_cache (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    source VARCHAR(50) NOT NULL,
    cache_key VARCHAR(128) NOT NULL,
    response_data LONGTEXT,
    expires_at INT UNSIGNED NOT NULL,
    created_at INT UNSIGNED NOT NULL,
    
    UNIQUE KEY unique_cache (source, cache_key),
    INDEX idx_expires (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================
-- MIGRATION: Upgrade existing v1 tables
-- ============================================

-- If venues table exists from v1, add new columns
SET @dbname = DATABASE();
SET @tablename = 'venues';
SET @column_exists = (
    SELECT COUNT(*) 
    FROM information_schema.columns 
    WHERE table_schema = @dbname 
    AND table_name = @tablename 
    AND column_name = 'metadata'
);

SET @sql = IF(@column_exists = 0, 
    'ALTER TABLE venues 
     ADD COLUMN sub_source VARCHAR(50) AFTER source,
     ADD COLUMN source_url VARCHAR(500) AFTER source_id,
     ADD COLUMN rating_count INT UNSIGNED DEFAULT 0 AFTER rating,
     ADD COLUMN county VARCHAR(50) AFTER zip,
     ADD COLUMN email VARCHAR(255) AFTER website,
     ADD COLUMN operating_status ENUM("open", "temporarily_closed", "permanently_closed", "seasonal", "coming_soon") DEFAULT "open" AFTER hours,
     ADD COLUMN hours_confirmed BOOLEAN DEFAULT FALSE AFTER operating_status,
     ADD COLUMN seasonal_notes VARCHAR(255) AFTER hours_confirmed,
     ADD COLUMN license_number VARCHAR(50),
     ADD COLUMN license_type VARCHAR(50),
     ADD COLUMN license_status ENUM("active", "inactive", "suspended", "expired") DEFAULT "active",
     ADD COLUMN inspection_score DECIMAL(4, 2),
     ADD COLUMN last_inspection_date DATE,
     ADD COLUMN inspection_violations INT DEFAULT 0,
     ADD COLUMN metadata JSON,
     ADD COLUMN confidence_score DECIMAL(3, 2) DEFAULT 0.50,
     ADD COLUMN data_freshness TINYINT DEFAULT 0,
     ADD COLUMN last_verified INT UNSIGNED',
    'SELECT "Already migrated" as status'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Add new indexes if they don't exist
SET @idx_exists = (
    SELECT COUNT(*) 
    FROM information_schema.statistics 
    WHERE table_schema = @dbname 
    AND table_name = @tablename 
    AND index_name = 'idx_verified'
);

SET @idx_sql = IF(@idx_exists = 0,
    'ALTER TABLE venues 
     ADD INDEX idx_verified (last_verified),
     ADD INDEX idx_city (city),
     ADD INDEX idx_county (county),
     ADD INDEX idx_operating (operating_status)',
    'SELECT "Indexes already exist" as status'
);

PREPARE idx_stmt FROM @idx_sql;
EXECUTE idx_stmt;
DEALLOCATE PREPARE idx_stmt;

-- Grant permissions
GRANT SELECT, INSERT, UPDATE, DELETE ON neutraleats.* TO 'neutraleats_user'@'localhost';
FLUSH PRIVILEGES;

-- Done!
SELECT 'Neutral Eats v2.0 schema upgrade complete!' as status;
