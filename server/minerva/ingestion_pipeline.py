#!/usr/bin/env python3
"""
Neutral Eats - Free API Ingestion Pipeline
Central Florida Priority -> Statewide -> Nationwide

Sources (all free tiers):
- Overture Maps (unlimited, no key)
- OSM Overpass (rate limited, no key)  
- Yelp Fusion (5,000 calls/day)
- Foursquare Places (free tier)

Architecture:
- Background ingestion only (no user-facing API calls)
- Stores in MySQL database
- Incremental updates with deduplication
- Rate limiting to respect free tiers
"""

import requests
import time
import json
import logging
from datetime import datetime
from typing import List, Dict, Optional
import mysql.connector
from mysql.connector import Error
import sys

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/www/html/minerva/data/ingestion.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Database config
DB_CONFIG = {
    'host': 'localhost',
    'user': 'neutraleats_user',
    'password': 'REDACTED',
    'database': 'neutraleats'
}

# API Keys (add these when ready)
YELP_API_KEY = 'REDACTED'  # Get from https://www.yelp.com/developers
FOURSQUARE_API_KEY = None  # Get from https://developer.foursquare.com/

# Rate limiting
RATE_LIMITS = {
    'overpass': 2,  # 2 seconds between calls
    'overture': 0.5,  # 2 calls per second
    'yelp': 0.02,  # 5000/day = ~1 call every 17 seconds
    'foursquare': 0.1  # 10 calls per second on free tier
}

last_call = {k: 0 for k in RATE_LIMITS.keys()}

def rate_limit(source: str):
    """Enforce rate limiting"""
    elapsed = time.time() - last_call[source]
    if elapsed < RATE_LIMITS[source]:
        sleep_time = RATE_LIMITS[source] - elapsed
        time.sleep(sleep_time)
    last_call[source] = time.time()

def get_db_connection():
    """Get MySQL connection"""
    try:
        return mysql.connector.connect(**DB_CONFIG)
    except Error as e:
        logger.error(f"Database connection failed: {e}")
        return None

def venue_exists(cursor, name: str, address: str, lat: float, lng: float) -> tuple:
    """
    Check if venue already exists (deduplication)
    Returns: (exists: bool, is_same_location: bool)
    
    Logic:
    - Same name + same address = duplicate (even if coordinates differ slightly)
    - Same name + different address = different venue (chain locations)
    - Same location (50m) + different name = different venue
    """
    # Normalize address for comparison (remove extra spaces, lowercase)
    norm_address = ' '.join(address.lower().split()) if address else ''
    
    # Check 1: Same name + same address = duplicate
    if norm_address:
        query = """
            SELECT id, lat, lng, address FROM venues 
            WHERE LOWER(name) = LOWER(%s)
            AND address IS NOT NULL
            AND LOWER(address) = LOWER(%s)
            LIMIT 1
        """
        cursor.execute(query, (name, address))
        result = cursor.fetchone()
        if result:
            return (True, True)  # Exists, same location
    
    # Check 2: Same name within 100m (possible coordinate drift)
    query = """
        SELECT id, lat, lng FROM venues 
        WHERE LOWER(name) = LOWER(%s)
        AND ABS(lat - %s) < 0.001 
        AND ABS(lng - %s) < 0.001
        LIMIT 1
    """
    cursor.execute(query, (name, lat, lng))
    result = cursor.fetchone()
    if result:
        return (True, True)  # Exists, same location
    
    # Check 3: Different name at same location = different venue
    query = """
        SELECT id FROM venues 
        WHERE ABS(lat - %s) < 0.0005 
        AND ABS(lng - %s) < 0.0005
        LIMIT 1
    """
    cursor.execute(query, (lat, lng))
    location_occupied = cursor.fetchone() is not None
    
    return (False, location_occupied)

def insert_venue(cursor, venue: Dict) -> bool:
    """Insert venue into database"""
    try:
        query = """
            INSERT INTO venues (
                name, lat, lng, type, cuisine, brand, rating, price_level,
                address, phone, website, source, source_id, raw_data,
                is_active, last_updated
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, 1, NOW()
            )
            ON DUPLICATE KEY UPDATE
                rating = VALUES(rating),
                price_level = VALUES(price_level),
                last_updated = NOW()
        """
        cursor.execute(query, (
            venue.get('name'),
            venue.get('lat'),
            venue.get('lng'),
            venue.get('type'),
            venue.get('cuisine'),
            venue.get('brand'),
            venue.get('rating'),
            venue.get('price_level'),
            venue.get('address'),
            venue.get('phone'),
            venue.get('website'),
            venue.get('source'),
            venue.get('source_id'),
            json.dumps(venue.get('raw_data', {}))
        ))
        return True
    except Error as e:
        logger.error(f"Insert failed: {e}")
        return False

# ============== OVERTURE MAPS (FREE, NO KEY) ==============

def fetch_overture_bbox(west: float, south: float, east: float, north: float) -> List[Dict]:
    """Fetch venues from Overture Maps via Fused"""
    rate_limit('overture')
    
    url = f"https://www.fused.io/server/v1/realtime-shared/UDF_Overture_Maps_Example/run/file"
    params = {
        'bbox': f"{west},{south},{east},{north}",
        'overture_type': 'place',
        'format': 'geojson'
    }
    
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        venues = []
        for feature in data.get('features', []):
            props = feature.get('properties', {})
            geom = feature.get('geometry', {})
            coords = geom.get('coordinates', [0, 0])
            
            # Skip non-food venues
            category = props.get('categories', {}).get('primary', '').lower()
            if not any(x in category for x in ['restaurant', 'food', 'cafe', 'bar', 'pub', 'bakery', 'coffee']):
                continue
            
            venue = {
                'name': props.get('names', {}).get('primary', 'Unknown'),
                'lat': coords[1],
                'lng': coords[0],
                'type': categorize_type(category),
                'cuisine': extract_cuisine(category),
                'brand': props.get('brand', {}).get('names', {}).get('primary', ''),
                'address': format_address(props.get('addresses', [{}])[0]),
                'phone': props.get('phone', ''),
                'website': props.get('websites', [''])[0] if isinstance(props.get('websites'), list) else '',
                'source': 'overture',
                'source_id': props.get('id', ''),
                'raw_data': props
            }
            venues.append(venue)
        
        logger.info(f"Overture: Found {len(venues)} venues in bbox")
        return venues
        
    except Exception as e:
        logger.error(f"Overture fetch failed: {e}")
        return []

# ============== OSM OVERPASS (FREE, NO KEY) ==============

def fetch_osm_bbox(west: float, south: float, east: float, north: float) -> List[Dict]:
    """Fetch venues from OpenStreetMap via Overpass"""
    rate_limit('overpass')
    
    overpass_query = f"""
    [out:json][timeout:60];
    (
      node["amenity"~"restaurant|cafe|bar|pub|fast_food|ice_cream|food_court|biergarten"]({south},{west},{north},{east});
      way["amenity"~"restaurant|cafe|bar|pub|fast_food|ice_cream|food_court|biergarten"]({south},{west},{north},{east});
      node["shop"~"bakery|confectionery|wine|deli|coffee"]({south},{west},{north},{east});
      way["shop"~"bakery|confectionery|wine|deli|coffee"]({south},{west},{north},{east});
    );
    out body center;
    >;
    out skel qt;
    """
    
    try:
        response = requests.post(
            'https://overpass-api.de/api/interpreter',
            data={'data': overpass_query},
            timeout=90
        )
        response.raise_for_status()
        data = response.json()
        
        venues = []
        for element in data.get('elements', []):
            if element.get('type') not in ['node', 'way']:
                continue
            
            tags = element.get('tags', {})
            
            # Get coordinates
            if element['type'] == 'node':
                lat, lng = element.get('lat'), element.get('lon')
            else:
                center = element.get('center', {})
                lat, lng = center.get('lat'), center.get('lon')
            
            if not lat or not lng:
                continue
            
            amenity = tags.get('amenity', '')
            shop = tags.get('shop', '')
            
            venue = {
                'name': tags.get('name', 'Unknown'),
                'lat': lat,
                'lng': lng,
                'type': categorize_type(f"{amenity} {shop}"),
                'cuisine': tags.get('cuisine', ''),
                'brand': tags.get('brand', tags.get('chain', '')),
                'address': format_osm_address(tags),
                'phone': tags.get('phone', tags.get('contact:phone', '')),
                'website': tags.get('website', tags.get('contact:website', '')),
                'source': 'osm',
                'source_id': str(element.get('id')),
                'raw_data': tags
            }
            venues.append(venue)
        
        logger.info(f"OSM: Found {len(venues)} venues in bbox")
        return venues
        
    except Exception as e:
        logger.error(f"OSM fetch failed: {e}")
        return []

# ============== YELP FUSION (5,000/day free) ==============

def fetch_yelp_location(lat: float, lng: float, radius: int = 1000) -> List[Dict]:
    """Fetch venues from Yelp Fusion API"""
    if not YELP_API_KEY:
        return []
    
    rate_limit('yelp')
    
    url = "https://api.yelp.com/v3/businesses/search"
    headers = {"Authorization": f"Bearer {YELP_API_KEY}"}
    params = {
        "latitude": lat,
        "longitude": lng,
        "radius": radius,
        "categories": "restaurants,food,cafes,bars",
        "limit": 50,
        "sort_by": "best_match"
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        venues = []
        for business in data.get('businesses', []):
            coords = business.get('coordinates', {})
            venue = {
                'name': business.get('name'),
                'lat': coords.get('latitude'),
                'lng': coords.get('longitude'),
                'type': categorize_type(business.get('categories', [{}])[0].get('title', '')),
                'cuisine': ', '.join([c.get('title', '') for c in business.get('categories', [])]),
                'brand': '',
                'rating': business.get('rating'),
                'price_level': len(business.get('price', '')),
                'address': ' '.join(business.get('location', {}).get('display_address', [])),
                'phone': business.get('phone', ''),
                'website': business.get('url', ''),
                'source': 'yelp',
                'source_id': business.get('id'),
                'raw_data': business
            }
            venues.append(venue)
        
        logger.info(f"Yelp: Found {len(venues)} venues near {lat},{lng}")
        return venues
        
    except Exception as e:
        logger.error(f"Yelp fetch failed: {e}")
        return []

# ============== FOURSQUARE (Free tier) ==============

def fetch_foursquare_location(lat: float, lng: float, radius: int = 1000) -> List[Dict]:
    """Fetch venues from Foursquare Places API"""
    if not FOURSQUARE_API_KEY:
        return []
    
    rate_limit('foursquare')
    
    url = "https://api.foursquare.com/v3/places/search"
    headers = {"Authorization": FOURSQUARE_API_KEY}
    params = {
        "ll": f"{lat},{lng}",
        "radius": radius,
        "categories": "13000",  # Dining & Drinking
        "limit": 50,
        "fields": "name,geocodes,location,tel,website,rating,price,categories"
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        venues = []
        for place in data.get('results', []):
            coords = place.get('geocodes', {}).get('main', {})
            venue = {
                'name': place.get('name'),
                'lat': coords.get('latitude'),
                'lng': coords.get('longitude'),
                'type': categorize_type(place.get('categories', [{}])[0].get('name', '')),
                'cuisine': ', '.join([c.get('name', '') for c in place.get('categories', [])]),
                'brand': '',
                'rating': place.get('rating'),
                'price_level': place.get('price'),
                'address': place.get('location', {}).get('formatted_address', ''),
                'phone': place.get('tel', ''),
                'website': place.get('website', ''),
                'source': 'foursquare',
                'source_id': place.get('fsq_id'),
                'raw_data': place
            }
            venues.append(venue)
        
        logger.info(f"Foursquare: Found {len(venues)} venues near {lat},{lng}")
        return venues
        
    except Exception as e:
        logger.error(f"Foursquare fetch failed: {e}")
        return []

# ============== HELPERS ==============

def categorize_type(category_str: str) -> str:
    """Normalize category to restaurant/cafe/bar/pub"""
    cat = category_str.lower()
    if any(x in cat for x in ['cafe', 'coffee', 'bakery']):
        return 'cafe'
    elif any(x in cat for x in ['bar', 'pub', 'biergarten', 'wine']):
        return 'bar'
    elif any(x in cat for x in ['fast_food', 'food_court']):
        return 'fast_food'
    else:
        return 'restaurant'

def extract_cuisine(category_str: str) -> str:
    """Extract cuisine type from category"""
    # This is simplified - could be enhanced
    cuisines = ['italian', 'chinese', 'mexican', 'japanese', 'thai', 'indian', 
                'american', 'pizza', 'burger', 'sushi', 'seafood']
    cat = category_str.lower()
    for cuisine in cuisines:
        if cuisine in cat:
            return cuisine
    return ''

def format_address(addr: Dict) -> str:
    """Format Overture address"""
    if not addr:
        return ''
    parts = [
        addr.get('street', ''),
        addr.get('city', ''),
        addr.get('region', ''),
        addr.get('postcode', '')
    ]
    return ', '.join(filter(None, parts))

def format_osm_address(tags: Dict) -> str:
    """Format OSM address tags"""
    parts = [
        tags.get('addr:housenumber', ''),
        tags.get('addr:street', ''),
        tags.get('addr:city', ''),
        tags.get('addr:state', ''),
        tags.get('addr:postcode', '')
    ]
    return ' '.join(filter(None, parts))

# ============== MAIN INGESTION ==============

# Central Florida Priority Grid (0.05 degree ~ 5km cells)
CENTRAL_FLORIDA_GRID = [
    # Orlando Core
    (-81.45, 28.50, -81.35, 28.60),  # Downtown/Dr Phillips
    (-81.35, 28.50, -81.25, 28.60),  # Winter Park
    (-81.25, 28.50, -81.15, 28.60),  # UCF/East Orlando
    (-81.45, 28.40, -81.35, 28.50),  # International Drive
    (-81.35, 28.40, -81.25, 28.50),  # Airport/South Orlando
    (-81.50, 28.60, -81.40, 28.70),  # North Orlando
    (-81.60, 28.30, -81.50, 28.40),  # Disney/Kissimmee
    (-81.50, 28.30, -81.40, 28.40),  # Kissimmee East
    
    # Suburbs
    (-81.40, 28.70, -81.30, 28.80),  # Altamonte/Lake Mary
    (-81.30, 28.60, -81.20, 28.70),  # Oviedo
    (-81.70, 28.40, -81.60, 28.50),  # Windermere
    (-81.60, 28.50, -81.50, 28.60),  # Ocoee
    
    # Tampa Bay
    (-82.50, 27.90, -82.40, 28.00),  # Downtown Tampa
    (-82.70, 27.90, -82.60, 28.00),  # Clearwater
    (-82.40, 27.90, -82.30, 28.00),  # Ybor/East Tampa
    (-82.70, 27.70, -82.60, 27.80),  # St Pete
]

def ingest_area(west: float, south: float, east: float, north: float,
                sources: List[str] = ['overture', 'osm'], 
                use_yelp_for_gaps: bool = True) -> int:
    """
    Ingest all venues from an area
    
    Strategy:
    1. Overture first (unlimited, high quality)
    2. OSM second (good coverage, fills gaps)
    3. Yelp only if coverage is still low (5k/day limit, use wisely)
    """
    logger.info(f"Processing bbox: {west},{south},{east},{north}")
    
    conn = get_db_connection()
    if not conn:
        return 0
    
    cursor = conn.cursor()
    added = 0
    
    # Phase 1: Overture (unlimited, no key needed)
    if 'overture' in sources:
        logger.info("Phase 1: Fetching from Overture Maps...")
        overture_venues = fetch_overture_bbox(west, south, east, north)
        for venue in overture_venues:
            exists, _ = venue_exists(cursor, venue['name'], venue.get('address', ''), venue['lat'], venue['lng'])
            if not exists:
                if insert_venue(cursor, venue):
                    added += 1
        logger.info(f"Overture: Added {added} venues so far")
    
    # Phase 2: OSM (good coverage, fills Overture gaps)
    if 'osm' in sources:
        logger.info("Phase 2: Fetching from OSM...")
        osm_added = 0
        osm_venues = fetch_osm_bbox(west, south, east, north)
        for venue in osm_venues:
            exists, _ = venue_exists(cursor, venue['name'], venue.get('address', ''), venue['lat'], venue['lng'])
            if not exists:
                if insert_venue(cursor, venue):
                    osm_added += 1
                    added += 1
        logger.info(f"OSM: Added {osm_added} venues")
    
    # Phase 3: Yelp for gaps (only if coverage is low and Yelp key available)
    if use_yelp_for_gaps and YELP_API_KEY and added < 20:
        logger.info(f"Phase 3: Coverage low ({added} venues), using Yelp to fill gaps...")
        yelp_added = 0
        # Query center of bbox with larger radius
        center_lat = (south + north) / 2
        center_lng = (west + east) / 2
        yelp_venues = fetch_yelp_location(center_lat, center_lng, radius=2000)
        for venue in yelp_venues:
            exists, _ = venue_exists(cursor, venue['name'], venue.get('address', ''), venue['lat'], venue['lng'])
            if not exists:
                if insert_venue(cursor, venue):
                    yelp_added += 1
                    added += 1
        logger.info(f"Yelp: Added {yelp_added} venues")
    
    conn.commit()
    cursor.close()
    conn.close()
    
    logger.info(f"Total added for this area: {added} venues")
    return added

def run_central_florida_pass():
    """Run ingestion for Central Florida priority areas"""
    logger.info("="*60)
    logger.info("Starting Central Florida Ingestion Pass")
    logger.info("="*60)
    
    total_added = 0
    
    for i, (west, south, east, north) in enumerate(CENTRAL_FLORIDA_GRID, 1):
        logger.info(f"\n[{i}/{len(CENTRAL_FLORIDA_GRID)}] Processing area...")
        added = ingest_area(west, south, east, north)
        total_added += added
        
        # Progress update every 5 cells
        if i % 5 == 0:
            logger.info(f"Progress: {i}/{len(CENTRAL_FLORIDA_GRID)} cells, {total_added} venues added")
    
    logger.info(f"\nCentral Florida pass complete! Total added: {total_added}")
    return total_added

def expand_to_statewide():
    """Expand to rest of Florida (to be implemented)"""
    logger.info("Statewide expansion not yet implemented")
    pass

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--central-fl":
        run_central_florida_pass()
    else:
        logger.info("Usage: python3 ingestion_pipeline.py --central-fl")
        logger.info("Add Yelp/Foursquare keys to enable those sources")
