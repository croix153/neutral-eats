#!/usr/bin/env python3
"""
Foursquare Places API Ingestion for Neutral Eats
Complements Yelp with additional venues
Free tier: 500+ calls/day
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
        logging.FileHandler('/var/www/html/minerva/data/foursquare_ingestion.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Add your Foursquare API key here
FOURSQUARE_API_KEY = None  # Get from https://developer.foursquare.com/

# Rate limit: ~10 calls per second on free tier
RATE_DELAY = 0.1
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
    source = venue.get('source', 'foursquare')
    source_id = escape_sql(venue.get('source_id', ''))[:100]
    lat = venue.get('lat') or 0
    lng = venue.get('lng') or 0
    rating = venue.get('rating') or 'NULL'
    price_level = venue.get('price_level') or 'NULL'
    
    query = f"INSERT INTO venues (id, name, lat, lng, type, cuisine, rating, price_level, address, phone, source, source_id, is_active, last_updated, first_seen, check_count) VALUES ('{source_id}', '{name}', {lat}, {lng}, 'restaurant', '{cuisine}', {rating}, {price_level}, '{address}', '{phone}', '{source}', '{source_id}', 1, UNIX_TIMESTAMP(), UNIX_TIMESTAMP(), 1) ON DUPLICATE KEY UPDATE rating = VALUES(rating), price_level = VALUES(price_level), last_updated = UNIX_TIMESTAMP()"
    
    result = mysql_execute(query)
    return 'error' not in result.lower()

def fetch_foursquare(lat: float, lng: float, radius: int = 2000) -> List[Dict]:
    if not FOURSQUARE_API_KEY:
        logger.error("No Foursquare API key set!")
        return []
    
    global last_call
    elapsed = time.time() - last_call
    if elapsed < RATE_DELAY:
        time.sleep(RATE_DELAY - elapsed)
    last_call = time.time()
    
    url = "https://api.foursquare.com/v3/places/search"
    headers = {"Authorization": FOURSQUARE_API_KEY}
    params = {
        "ll": f"{lat},{lng}",
        "radius": radius,
        "categories": "13065",  # Restaurant category
        "limit": 50,
        "fields": "name,geocodes,location,categories,rating,price,tel"
    }
    
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        stats['calls'] += 1
        if resp.status_code == 200:
            return resp.json().get('results', [])
        elif resp.status_code == 429:
            logger.warning("Foursquare rate limited, backing off...")
            time.sleep(60)
        else:
            logger.error(f"Foursquare error: {resp.status_code}")
    except Exception as e:
        logger.error(f"Foursquare fetch error: {e}")
    return []

def fsq_to_venue(result: Dict) -> Optional[Dict]:
    try:
        geocodes = result.get('geocodes', {}).get('main', {})
        location = result.get('location', {})
        categories = result.get('categories', [])
        
        return {
            'name': result.get('name', 'Unknown'),
            'lat': geocodes.get('latitude'),
            'lng': geocodes.get('longitude'),
            'cuisine': ', '.join([c.get('name', '') for c in categories]),
            'rating': result.get('rating', {}).get('score'),
            'price_level': result.get('price'),
            'address': location.get('formatted_address', ''),
            'phone': result.get('tel', ''),
            'source': 'foursquare',
            'source_id': result.get('fsq_id', '')
        }
    except Exception as e:
        logger.error(f"Parse error: {e}")
        return None

def ingest_fsq_area(name: str, lat: float, lng: float, radius: int = 3000):
    logger.info(f"Processing {name}...")
    area_new = 0
    
    results = fetch_foursquare(lat, lng, radius)
    
    for r in results:
        venue = fsq_to_venue(r)
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

# Target areas (same as Yelp script)
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
    if not FOURSQUARE_API_KEY:
        logger.error("="*70)
        logger.error("NO FOURSQUARE API KEY SET!")
        logger.error("Get one at: https://developer.foursquare.com/")
        logger.error("Add it to FOURSQUARE_API_KEY variable in this script")
        logger.error("="*70)
        return
    
    logger.info("="*70)
    logger.info("FOURSQUARE INGESTION STARTED")
    logger.info("="*70)
    
    for area in ORLANDO_AREAS:
        ingest_fsq_area(area['name'], area['lat'], area['lng'])
    
    logger.info("="*70)
    logger.info(f"COMPLETE: {stats['new_venues']} new venues added")
    logger.info(f"API calls: {stats['calls']} | Duplicates: {stats['duplicates']}")
    logger.info("="*70)

if __name__ == "__main__":
    main()
