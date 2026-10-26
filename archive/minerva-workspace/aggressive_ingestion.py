#!/usr/bin/env python3
"""
AGGRESSIVE Multi-API Restaurant Ingestion for Neutral Eats
Uses subprocess to call mysql directly (no Python mysql module needed)
Targets: Orlando/Central Florida priority, then Florida, then top 50 metros
"""

import requests
import json
import time
import logging
import subprocess
import shlex
from datetime import datetime
from typing import List, Dict, Optional

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/www/html/minerva/data/aggressive_ingestion.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# API Key
YELP_API_KEY = 'REDACTED'

# Rate limiting
YELP_DELAY = 17  # 5,000/day = 1 per 17 seconds
last_yelp_call = 0
stats = {'yelp_calls': 0, 'new_venues': 0, 'duplicates': 0}

def mysql_execute(query: str) -> str:
    """Execute MySQL query via subprocess"""
    cmd = f"mysql -u neutraleats_user -pneutraleats_pass neutraleats -e {shlex.quote(query)}"
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        return result.stdout + result.stderr
    except Exception as e:
        logger.error(f"MySQL error: {e}")
        return ""

def escape_sql(value: str) -> str:
    """Escape single quotes for SQL"""
    if not value:
        return ''
    return value.replace("'", "''")

def venue_exists(name: str, lat: float, lng: float) -> bool:
    """Check for duplicates within ~100m using haversine approximation"""
    safe_name = escape_sql(name)
    query = f"SELECT id FROM venues WHERE LOWER(name) = LOWER('{safe_name}') AND ABS(lat - {lat}) < 0.001 AND ABS(lng - {lng}) < 0.001 LIMIT 1"
    result = mysql_execute(query)
    return 'id' in result or len(result.strip().split('\n')) > 1

def insert_venue(venue: Dict) -> bool:
    """Insert venue using mysql command line"""
    name = escape_sql(venue.get('name', 'Unknown'))
    cuisine = escape_sql(venue.get('cuisine', ''))[:100]
    address = escape_sql(venue.get('address', ''))[:255]
    phone = escape_sql(venue.get('phone', ''))[:20]
    source = venue.get('source', 'yelp')
    source_id = escape_sql(venue.get('source_id', ''))[:100]
    lat = venue.get('lat') or 0
    lng = venue.get('lng') or 0
    rating = venue.get('rating') or 'NULL'
    price_level = venue.get('price_level') or 'NULL'
    
    query = f"INSERT INTO venues (id, name, lat, lng, type, cuisine, rating, price_level, address, phone, source, source_id, is_active, last_updated, first_seen, check_count) VALUES ('{source_id}', '{name}', {lat}, {lng}, 'restaurant', '{cuisine}', {rating}, {price_level}, '{address}', '{phone}', '{source}', '{source_id}', 1, UNIX_TIMESTAMP(), UNIX_TIMESTAMP(), 1) ON DUPLICATE KEY UPDATE rating = VALUES(rating), price_level = VALUES(price_level), last_updated = UNIX_TIMESTAMP()"
    
    result = mysql_execute(query)
    return 'error' not in result.lower()

def fetch_yelp(lat: float, lng: float, radius: int = 2000, offset: int = 0) -> List[Dict]:
    """Fetch restaurants from Yelp"""
    global last_yelp_call
    elapsed = time.time() - last_yelp_call
    if elapsed < YELP_DELAY:
        time.sleep(YELP_DELAY - elapsed)
    last_yelp_call = time.time()
    
    url = "https://api.yelp.com/v3/businesses/search"
    headers = {"Authorization": f"Bearer {YELP_API_KEY}"}
    params = {
        "latitude": lat, "longitude": lng, "radius": radius,
        "categories": "restaurants,food", "limit": 50, "offset": offset
    }
    
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        stats['yelp_calls'] += 1
        if resp.status_code == 200:
            return resp.json().get('businesses', [])
        elif resp.status_code == 429:
            logger.warning("Yelp rate limited, backing off 60s...")
            time.sleep(60)
        else:
            logger.error(f"Yelp error: {resp.status_code}")
    except Exception as e:
        logger.error(f"Yelp fetch error: {e}")
    return []

def yelp_to_venue(b: Dict) -> Optional[Dict]:
    """Convert Yelp business to venue format"""
    try:
        coords = b.get('coordinates', {})
        loc = b.get('location', {})
        price = b.get('price', '')
        return {
            'name': b.get('name', 'Unknown'),
            'lat': coords.get('latitude'),
            'lng': coords.get('longitude'),
            'cuisine': ', '.join([c.get('title', '') for c in b.get('categories', [])]),
            'rating': b.get('rating'),
            'price_level': len(price) if price else None,
            'address': ', '.join(loc.get('display_address', [])),
            'phone': b.get('display_phone', '').replace('+', '') if b.get('display_phone') else '',
            'source': 'yelp',
            'source_id': b.get('id')
        }
    except Exception as e:
        logger.error(f"Parse error: {e}")
        return None

def ingest_area(name: str, lat: float, lng: float, radius: int = 3000):
    """Ingest all venues from an area"""
    logger.info(f"Processing {name}...")
    area_new = 0
    
    for offset in range(0, 1000, 50):  # Max 1000 results per area
        businesses = fetch_yelp(lat, lng, radius, offset)
        if not businesses:
            break
        
        for b in businesses:
            venue = yelp_to_venue(b)
            if not venue or not venue.get('lat') or not venue.get('lng'):
                continue
            
            if venue_exists(venue['name'], venue['lat'], venue['lng']):
                stats['duplicates'] += 1
                continue
            
            if insert_venue(venue):
                area_new += 1
                stats['new_venues'] += 1
        
        logger.info(f"  Offset {offset}: +{area_new} new (total: {stats['new_venues']})")
        
        if len(businesses) < 50:  # No more results
            break
    
    logger.info(f"Done {name}: +{area_new} new venues")
    return area_new

# ============ TARGET AREAS ============
ORLANDO_AREAS = [
    {"name": "Downtown Orlando", "lat": 28.5383, "lng": -81.3792, "radius": 3000},
    {"name": "Winter Park", "lat": 28.5978, "lng": -81.3516, "radius": 2500},
    {"name": "Lake Mary", "lat": 28.7589, "lng": -81.3178, "radius": 3000},
    {"name": "Altamonte Springs", "lat": 28.6611, "lng": -81.3656, "radius": 2500},
    {"name": "Maitland", "lat": 28.6278, "lng": -81.3631, "radius": 2000},
    {"name": "Sanford", "lat": 28.8027, "lng": -81.2694, "radius": 3000},
    {"name": "Kissimmee", "lat": 28.2920, "lng": -81.4076, "radius": 3000},
    {"name": "Celebration", "lat": 28.3136, "lng": -81.5332, "radius": 2000},
    {"name": "Winter Garden", "lat": 28.5653, "lng": -81.5862, "radius": 2500},
    {"name": "Ocoee", "lat": 28.5692, "lng": -81.5440, "radius": 2500},
    {"name": "Clermont", "lat": 28.5494, "lng": -81.7729, "radius": 2500},
    {"name": "Apopka", "lat": 28.6761, "lng": -81.5116, "radius": 2500},
    {"name": "Longwood", "lat": 28.7031, "lng": -81.3384, "radius": 2000},
    {"name": "Oviedo", "lat": 28.6700, "lng": -81.2081, "radius": 2500},
    {"name": "Casselberry", "lat": 28.6775, "lng": -81.3278, "radius": 2000},
    {"name": "Winter Springs", "lat": 28.6983, "lng": -81.2792, "radius": 2000},
    {"name": "Disney Springs", "lat": 28.3703, "lng": -81.5212, "radius": 2000},
    {"name": "I-Drive Orlando", "lat": 28.4500, "lng": -81.4700, "radius": 3000},
    {"name": "Dr Phillips", "lat": 28.4289, "lng": -81.4736, "radius": 2500},
    {"name": "Millenia Orlando", "lat": 28.4847, "lng": -81.4331, "radius": 2500},
]

FLORIDA_CITIES = [
    {"name": "Tampa Downtown", "lat": 27.9506, "lng": -82.4572, "radius": 4000},
    {"name": "St Petersburg FL", "lat": 27.7676, "lng": -82.6403, "radius": 3500},
    {"name": "Clearwater FL", "lat": 27.9659, "lng": -82.8001, "radius": 3500},
    {"name": "Ybor City", "lat": 27.9607, "lng": -82.4417, "radius": 2000},
    {"name": "Miami Downtown", "lat": 25.7617, "lng": -80.1918, "radius": 4000},
    {"name": "Miami Beach", "lat": 25.7907, "lng": -80.1300, "radius": 3000},
    {"name": "Brickell Miami", "lat": 25.7594, "lng": -80.1911, "radius": 2500},
    {"name": "Wynwood Miami", "lat": 25.8042, "lng": -80.1992, "radius": 2000},
    {"name": "Fort Lauderdale", "lat": 26.1224, "lng": -80.1373, "radius": 4000},
    {"name": "Boca Raton", "lat": 26.3683, "lng": -80.1289, "radius": 3500},
    {"name": "West Palm Beach", "lat": 26.7153, "lng": -80.0534, "radius": 3500},
    {"name": "Jacksonville", "lat": 30.3322, "lng": -81.6557, "radius": 4000},
    {"name": "Gainesville FL", "lat": 29.6516, "lng": -82.3248, "radius": 3500},
    {"name": "Daytona Beach", "lat": 29.2108, "lng": -81.0228, "radius": 3000},
    {"name": "Melbourne FL", "lat": 28.0836, "lng": -80.6081, "radius": 3000},
    {"name": "Naples FL", "lat": 26.1420, "lng": -81.7948, "radius": 3000},
    {"name": "Sarasota", "lat": 27.3364, "lng": -82.5307, "radius": 3000},
    {"name": "Tallahassee", "lat": 30.4383, "lng": -84.2807, "radius": 3500},
]

def get_current_count():
    """Get current venue count"""
    result = mysql_execute("SELECT COUNT(*) FROM venues")
    try:
        lines = result.strip().split('\n')
        for line in lines:
            if line.isdigit():
                return int(line)
        return 0
    except:
        return 0

def main():
    """Main ingestion loop"""
    logger.info("="*70)
    logger.info("AGGRESSIVE YELP INGESTION STARTED")
    logger.info("="*70)
    
    start_count = get_current_count()
    logger.info(f"Starting count: {start_count:,} venues")
    
    # Phase 1: Orlando/Central Florida (highest priority)
    logger.info("PHASE 1: ORLANDO/CENTRAL FLORIDA")
    for area in ORLANDO_AREAS:
        ingest_area(area['name'], area['lat'], area['lng'], area['radius'])
    
    # Phase 2: Florida statewide
    logger.info("PHASE 2: FLORIDA STATEWIDE")
    for area in FLORIDA_CITIES:
        ingest_area(area['name'], area['lat'], area['lng'], area['radius'])
    
    # Final stats
    end_count = get_current_count()
    logger.info("="*70)
    logger.info(f"INGESTION COMPLETE")
    logger.info(f"Started: {start_count:,} | Ended: {end_count:,} | Added: {end_count - start_count:,}")
    logger.info(f"Yelp calls: {stats['yelp_calls']} | Duplicates skipped: {stats['duplicates']}")
    logger.info("="*70)

if __name__ == "__main__":
    main()
