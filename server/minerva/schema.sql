-- Neutral Eats Database Schema
-- SQLite database for cached restaurant/venue data

-- Main venues table
CREATE TABLE venues (
    id TEXT PRIMARY KEY,                    -- Unique ID (source:overture_id or osm:node_id)
    name TEXT NOT NULL,                     -- Venue name
    lat REAL NOT NULL,                      -- Latitude
    lng REAL NOT NULL,                      -- Longitude
    type TEXT NOT NULL,                     -- restaurant, cafe, bar, etc.
    cuisine TEXT,                           -- Cuisine type
    brand TEXT,                             -- Brand/chain name
    source TEXT NOT NULL,                   -- 'overture' or 'osm'
    source_id TEXT,                         -- Original ID from source
    rating REAL,                            -- Rating if available
    price_level INTEGER,                    -- 1-4 price level
    address TEXT,                           -- Street address
    city TEXT,                              -- City
    state TEXT,                             -- State
    zip TEXT,                               -- ZIP code
    phone TEXT,                             -- Phone number
    website TEXT,                           -- Website URL
    hours TEXT,                             -- Opening hours (JSON)
    photos TEXT,                            -- Photo URLs (JSON array)
    last_updated INTEGER NOT NULL,          -- Unix timestamp
    first_seen INTEGER NOT NULL,            -- Unix timestamp
    is_active INTEGER DEFAULT 1,            -- 1=active, 0=closed/deleted
    check_count INTEGER DEFAULT 1,          -- How many times verified
    grid_cell TEXT                          -- Grid cell key for indexing
);

-- Grid cells for spatial indexing
CREATE TABLE grid_cells (
    cell_key TEXT PRIMARY KEY,              -- "lat,lng" grid identifier
    lat_min REAL NOT NULL,
    lat_max REAL NOT NULL,
    lng_min REAL NOT NULL,
    lng_max REAL NOT NULL,
    venue_count INTEGER DEFAULT 0,
    last_fetched INTEGER,                   -- When this cell was last updated
    next_fetch INTEGER,                     -- When to fetch again
    fetch_count INTEGER DEFAULT 0
);

-- Sync log for tracking data refreshes
CREATE TABLE sync_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,                   -- 'overture', 'overpass', 'manual'
    grid_cell TEXT,
    venues_added INTEGER DEFAULT 0,
    venues_updated INTEGER DEFAULT 0,
    venues_removed INTEGER DEFAULT 0,
    started_at INTEGER NOT NULL,
    completed_at INTEGER,
    status TEXT,                            -- 'running', 'success', 'error'
    error_message TEXT
);

-- Pending updates (for incremental refreshes)
CREATE TABLE pending_updates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    venue_id TEXT NOT NULL,
    update_type TEXT NOT NULL,              -- 'refresh', 'verify', 'remove'
    priority INTEGER DEFAULT 0,             -- Higher = more urgent
    created_at INTEGER NOT NULL,
    processed_at INTEGER,
    FOREIGN KEY (venue_id) REFERENCES venues(id)
);

-- Indexes for performance
CREATE INDEX idx_venues_location ON venues(lat, lng);
CREATE INDEX idx_venues_type ON venues(type);
CREATE INDEX idx_venues_grid ON venues(grid_cell);
CREATE INDEX idx_venues_active ON venues(is_active);
CREATE INDEX idx_venues_source ON venues(source);
CREATE INDEX idx_venues_updated ON venues(last_updated);
CREATE INDEX idx_sync_log_time ON sync_log(started_at);
CREATE INDEX idx_grid_cells_fetch ON grid_cells(next_fetch);

-- Full-text search index
CREATE VIRTUAL TABLE venues_search USING fts5(
    name,
    cuisine,
    brand,
    address,
    content='venues',
    content_rowid='rowid'
);

-- Triggers to keep search index in sync
CREATE TRIGGER venues_search_insert AFTER INSERT ON venues BEGIN
    INSERT INTO venues_search(rowid, name, cuisine, brand, address)
    VALUES (new.rowid, new.name, new.cuisine, new.brand, new.address);
END;

CREATE TRIGGER venues_search_update AFTER UPDATE ON venues BEGIN
    INSERT INTO venues_search(venues_search, rowid, name, cuisine, brand, address)
    VALUES ('delete', old.rowid, old.name, old.cuisine, old.brand, old.address);
    INSERT INTO venues_search(rowid, name, cuisine, brand, address)
    VALUES (new.rowid, new.name, new.cuisine, new.brand, new.address);
END;

CREATE TRIGGER venues_search_delete AFTER DELETE ON venues BEGIN
    INSERT INTO venues_search(venues_search, rowid, name, cuisine, brand, address)
    VALUES ('delete', old.rowid, old.name, old.cuisine, old.brand, old.address);
END;