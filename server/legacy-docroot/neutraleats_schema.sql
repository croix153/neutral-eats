CREATE TABLE IF NOT EXISTS venues (
    id TEXT PRIMARY KEY,
    name TEXT,
    lat REAL,
    lng REAL,
    type TEXT,
    cuisine TEXT,
    brand TEXT,
    source TEXT,
    source_id TEXT,
    last_updated INTEGER,
    first_seen INTEGER,
    grid_cell TEXT,
    check_count INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS grid_cells (
    cell_key TEXT PRIMARY KEY,
    lat_min REAL,
    lat_max REAL,
    lng_min REAL,
    lng_max REAL,
    venue_count INTEGER,
    last_fetched INTEGER,
    next_fetch INTEGER,
    fetch_count INTEGER DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_venues_grid_cell ON venues(grid_cell);
CREATE INDEX IF NOT EXISTS idx_venues_location ON venues(lat, lng);
