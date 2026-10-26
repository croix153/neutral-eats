#!/usr/bin/env python3
"""
Google Places API Ingestion for Neutral Eats
$200 free monthly credit = ~40,000 place details calls
Complements Yelp + Foursquare coverage
"""

import requests
import json
import time
import logging
import subprocess
from typing import List, Dict, Optional

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/www/html/minerva/data/google_ingestion.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Add your Google Places API key here
GOOGLE_API_KEY = None  # Get from https://developers.google.com/maps/documentation/places/web-service

# Rate limit: generous on paid tier, conservative here
RATE_DELAY = 0.05  # 20 calls per second
last_call = 0
stats = {'calls': 0, 'new_venues': 0, 'duplicates': 0}

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
    source = venue.get('source', 'google')
    source_id = escape_sql(venue.get('source_id', ''))[:100]
    lat = venue.get('lat') or 0
    lng = venue.get('lng') or 0
    rating = venue.get('rating') or 'NULL'
    price_level = venue.get('price_level') or 'NULL'
    
    query = f"INSERT INTO venues (id, name, lat, lng, type, cuisine, rating, price_level, address, phone, source, source_id, is_active, last_updated, first_seen, check_count) VALUES ('{source_id}', '{name}', {lat}, {lng}, 'restaurant', '{cuisine}', {rating}, {price_level}, '{address}', '{phone}', '{source}', '{source_id}', 1, UNIX_TIMESTAMP(), UNIX_TIMESTAMP(), 1) ON DUPLICATE KEY UPDATE rating = VALUES(rating), price_level = VALUES(price_level), last_updated = UNIX_TIMESTAMP()"
    
    result = mysql_execute(query)
    return 'error' not in result.lower()

def fetch_google_nearby(lat: float, lng: float, radius: int = 2000) -> List[Dict]:
    if not GOOGLE_API_KEY:
        logger.error("No Google API key set!")
        return []
    
    global last_call
    elapsed = time.time() - last_call
    if elapsed < RATE_DELAY:
        time.sleep(RATE_DELAY - elapsed)
    last_call = time.time()
    
    url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    params = {
        "location": f"{lat},{lng}",
        "radius": radius,
        "type": "restaurant",
        "key": GOOGLE_API_KEY
    }
    
    try:
        resp = requests.get(url, params=params, timeout=30)
        stats['calls'] += 1
        data = resp.json()
        if data.get('status') == 'OK':
            return data.get('results', [])
        elif data.get('status') == 'OVER_QUERY_LIMIT':
            logger.warning("Google rate limited, backing off...")
            time.sleep(60)
        else:
            logger.error(f"Google error: {data.get('status')}")
    except Exception as e:
        logger.error(f"Google fetch error: {e}")
    return []

def google_to_venue(result: Dict) -> Optional[Dict]:
    try:
        geom = result.get('geometry', {}).get('location', {})
        
        # Get price level (0-4 scale)
        price = result.get('price_level')
        
        return {
            'name': result.get('name', 'Unknown'),
            'lat': geom.get('lat'),
            'lng': geom.get('lng'),
            'cuisine': ', '.join(result.get('types', [])).replace('_', ' '),
            'rating': result.get('rating'),
            'price_level': price,
            'address': result.get('vicinity', ''),
            'phone': '',  # Requires separate details call
            'source': 'google',
            'source_id': result.get('place_id', '')
        }
    except Exception as e:
        logger.error(f"Parse error: {e}")
        return None

def ingest_google_area(name: str, lat: float, lng: float, radius: int = 2000):
    logger.info(f"Processing {name}...")
    area_new = 0
    
    results = fetch_google_nearby(lat, lng, radius)
    
    for r in results:
        venue = google_to_venue(r)
        if not venue or not venue.get('lat') or not venue.get('lng'):
            continue
        
        if venue_exists(venue['name'], venue['lat'], venue['lng']):
            stats['duplicates'] += 1
            continue
        
        if insert_venue(venue):
            area_new += 1
            stats['new_venues'] += 1
    
    logger.info(f"Done {name}: +{area_new} new venues (total: {stats['new_venues']})")
    return area_new

# Target areas
ORLANDO_AREAS = [
    {"name": "Downtown Orlando", "lat": 28.5383, "lng": -81.3792},
    {"name": "Winter Park", "lat": 28.5978, "lng": -81.3516},
    {"name": "Lake Mary", "lat": 28.7589, "lng": -81.3178},
    {"name": "Altamonte Springs", "lat": 28.6611, "lng": -81.3656},
    {"name": "Maitland", "lat": 28.6278, "lng": -81.3631},
    {"name": "Sanford", "lat": 28.8027, "lng": -81.2694},
    {"name": "Kissimmee", "lat": 28.2920, "lng": -81.4076},
    {"name": "Celebration", "lat": 28.3136, "lng": -81.5332},
    {"name": "Winter Garden", "lat": 28.5653, "lng": -81.5862},
    {"name": "Ocoee", "lat": 28.5692, "lng": -81.5440},
    {"name": "Clermont", "lat": 28.5494, "lng": -81.7729},
    {"name": "Apopka", "lat": 28.6761, "lng": -81.5116},
    {"name": "Longwood", "lat": 28.7031, "lng": -81.3384},
    {"name": "Oviedo", "lat": 28.6700, "lng": -81.2081},
    {"name": "Casselberry", "lat": 28.6775, "lng": -81.3278},
    {"name": "Winter Springs", "lat": 28.6983, "lng": -81.2792},
    {"name": "Disney Springs", "lat": 28.3703, "lng": -81.5212},
    {"name": "I-Drive Orlando", "lat": 28.4500, "lng": -81.4700},
    {"name": "Dr Phillips", "lat": 28.4289, "lng": -81.4736},
    {"name": "Millenia Orlando", "lat": 28.4847, "lng": -81.4331},
]

def main():
    if not GOOGLE_API_KEY:
        logger.error("="*70)
        logger.error("NO GOOGLE PLACES API KEY SET!")
        logger.error("Get one at: https://developers.google.com/maps/documentation/places/web-service")
        logger.error("Free tier: $200 monthly credit")
        logger.error("="*70)
        return
    
    logger.info("="*70)
    logger.info("GOOGLE PLACES INGESTION STARTED")
    logger.info("="*70)
    
    for area in ORLANDO_AREAS:
        ingest_google_area(area['name'], area['lat'], area['lng'])
    
    logger.info("="*70)
    logger.info(f"COMPLETE: {stats['new_venues']} new venues added")
    logger.info(f"API calls: {stats['calls']} | Duplicates: {stats['duplicates']}")
    logger.info("="*70)

if __name__ == "__main__":
    main()
