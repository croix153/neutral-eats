#!/usr/bin/env python3
"""
Nationwide Restaurant Ingestion - Top 50 US Metros
Expands Neutral Eats to major cities across the US
Uses Yelp API with intelligent coverage gap detection
"""

import requests
import json
import time
import logging
import subprocess
from datetime import datetime
from typing import List, Dict, Optional

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/www/html/minerva/data/nationwide_ingestion.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

YELP_API_KEY = 'REDACTED'
YELP_DELAY = 17  # 5,000/day = 1 per 17 seconds
last_call = 0
stats = {'yelp_calls': 0, 'new_venues': 0, 'duplicates': 0, 'areas_processed': 0}

def mysql_execute(query: str) -> str:
    cmd = f"mysql -u neutraleats_user -pneutraleats_pass neutraleats -e '{query}'"
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        return result.stdout + result.stderr
    except Exception as e:
        logger.error(f"MySQL error: {e}")
        return ""

def escape_sql(value: str) -> str:
    if not value:
        return ''
    return value.replace("'", "''")

def venue_exists(name: str, lat: float, lng: float) -> bool:
    safe_name = escape_sql(name)
    query = f"SELECT id FROM venues WHERE LOWER(name) = LOWER('{safe_name}') AND ABS(lat - {lat}) < 0.001 AND ABS(lng - {lng}) < 0.001 LIMIT 1"
    result = mysql_execute(query)
    return 'id' in result or len(result.strip().split('\n')) > 1

def insert_venue(venue: Dict) -> bool:
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
    global last_call
    elapsed = time.time() - last_call
    if elapsed < YELP_DELAY:
        time.sleep(YELP_DELAY - elapsed)
    last_call = time.time()
    
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

def ingest_area(name: str, lat: float, lng: float, radius: int = 4000):
    logger.info(f"Processing {name}...")
    area_new = 0
    stats['areas_processed'] += 1
    
    for offset in range(0, 1000, 50):
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
        
        if len(businesses) < 50:
            break
    
    logger.info(f"Done {name}: +{area_new} new venues (total new: {stats['new_venues']})")
    return area_new

# Top 50 US Metro Areas
TOP_50_METROS = [
    {"name": "New York City", "lat": 40.7128, "lng": -74.0060, "radius": 8000},
    {"name": "Los Angeles", "lat": 34.0522, "lng": -118.2437, "radius": 10000},
    {"name": "Chicago", "lat": 41.8781, "lng": -87.6298, "radius": 9000},
    {"name": "Houston", "lat": 29.7604, "lng": -95.3698, "radius": 8000},
    {"name": "Phoenix", "lat": 33.4484, "lng": -112.0740, "radius": 7000},
    {"name": "Philadelphia", "lat": 39.9526, "lng": -75.1652, "radius": 7000},
    {"name": "San Antonio", "lat": 29.4241, "lng": -98.4936, "radius": 6000},
    {"name": "San Diego", "lat": 32.7157, "lng": -117.1611, "radius": 6000},
    {"name": "Dallas", "lat": 32.7767, "lng": -96.7970, "radius": 8000},
    {"name": "San Jose", "lat": 37.3382, "lng": -121.8863, "radius": 6000},
    {"name": "Austin", "lat": 30.2672, "lng": -97.7431, "radius": 6000},
    {"name": "Jacksonville", "lat": 30.3322, "lng": -81.6557, "radius": 6000},
    {"name": "Fort Worth", "lat": 32.7555, "lng": -97.3308, "radius": 6000},
    {"name": "Columbus", "lat": 39.9612, "lng": -82.9988, "radius": 5500},
    {"name": "Charlotte", "lat": 35.2271, "lng": -80.8431, "radius": 5500},
    {"name": "Indianapolis", "lat": 39.7684, "lng": -86.1581, "radius": 5500},
    {"name": "San Francisco", "lat": 37.7749, "lng": -122.4194, "radius": 6000},
    {"name": "Seattle", "lat": 47.6062, "lng": -122.3321, "radius": 6000},
    {"name": "Denver", "lat": 39.7392, "lng": -104.9903, "radius": 6000},
    {"name": "Washington DC", "lat": 38.9072, "lng": -77.0369, "radius": 8000},
    {"name": "Boston", "lat": 42.3601, "lng": -71.0589, "radius": 7000},
    {"name": "El Paso", "lat": 31.7619, "lng": -106.4850, "radius": 5000},
    {"name": "Nashville", "lat": 36.1627, "lng": -86.7816, "radius": 6000},
    {"name": "Detroit", "lat": 42.3314, "lng": -83.0458, "radius": 6500},
    {"name": "Oklahoma City", "lat": 35.4676, "lng": -97.5164, "radius": 5500},
    {"name": "Portland", "lat": 45.5152, "lng": -122.6784, "radius": 6000},
    {"name": "Las Vegas", "lat": 36.1699, "lng": -115.1398, "radius": 6000},
    {"name": "Louisville", "lat": 38.2527, "lng": -85.7585, "radius": 5500},
    {"name": "Baltimore", "lat": 39.2904, "lng": -76.6122, "radius": 6000},
    {"name": "Milwaukee", "lat": 43.0389, "lng": -87.9065, "radius": 5500},
    {"name": "Albuquerque", "lat": 35.0844, "lng": -106.6504, "radius": 5500},
    {"name": "Tucson", "lat": 32.2226, "lng": -110.9747, "radius": 5000},
    {"name": "Fresno", "lat": 36.7378, "lng": -119.7871, "radius": 5000},
    {"name": "Sacramento", "lat": 38.5816, "lng": -121.4944, "radius": 6000},
    {"name": "Kansas City", "lat": 39.0997, "lng": -94.5786, "radius": 6000},
    {"name": "Long Beach", "lat": 33.7701, "lng": -118.1937, "radius": 5000},
    {"name": "Mesa", "lat": 33.4152, "lng": -111.8315, "radius": 5000},
    {"name": "Atlanta", "lat": 33.7490, "lng": -84.3880, "radius": 8000},
    {"name": "Colorado Springs", "lat": 38.8339, "lng": -104.8214, "radius": 5000},
    {"name": "Virginia Beach", "lat": 36.8529, "lng": -75.9780, "radius": 5000},
    {"name": "Raleigh", "lat": 35.7796, "lng": -78.6382, "radius": 5500},
    {"name": "Omaha", "lat": 41.2565, "lng": -95.9345, "radius": 5000},
    {"name": "Minneapolis", "lat": 44.9778, "lng": -93.2650, "radius": 6000},
    {"name": "Tulsa", "lat": 36.1540, "lng": -95.9928, "radius": 5000},
    {"name": "Arlington TX", "lat": 32.7357, "lng": -97.1081, "radius": 5000},
    {"name": "New Orleans", "lat": 29.9511, "lng": -90.0715, "radius": 5500},
    {"name": "Wichita", "lat": 37.6872, "lng": -97.3301, "radius": 5000},
    {"name": "Cleveland", "lat": 41.4993, "lng": -81.6944, "radius": 5500},
    {"name": "Bakersfield", "lat": 35.3733, "lng": -119.0187, "radius": 5000},
    {"name": "Aurora CO", "lat": 39.7294, "lng": -104.8319, "radius": 5000},
]

def get_current_count():
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
    logger.info("="*70)
    logger.info("NATIONWIDE INGESTION - TOP 50 US METROS")
    logger.info("="*70)
    
    start_count = get_current_count()
    logger.info(f"Starting count: {start_count:,} venues")
    
    for i, metro in enumerate(TOP_50_METROS, 1):
        logger.info(f"\n[{i}/50] Processing {metro['name']}...")
        ingest_area(metro['name'], metro['lat'], metro['lng'], metro['radius'])
        
        # Progress report every 5 cities
        if i % 5 == 0:
            current = get_current_count()
            logger.info(f"\n📊 PROGRESS: {i}/50 metros | {current:,} total venues (+{current - start_count:,} new)")
    
    end_count = get_current_count()
    logger.info("\n" + "="*70)
    logger.info(f"NATIONWIDE INGESTION COMPLETE")
    logger.info(f"Started: {start_count:,} | Ended: {end_count:,} | Added: {end_count - start_count:,}")
    logger.info(f"Areas processed: {stats['areas_processed']} | Yelp calls: {stats['yelp_calls']}")
    logger.info(f"Duplicates skipped: {stats['duplicates']}")
    logger.info("="*70)

if __name__ == "__main__":
    main()
