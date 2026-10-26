#!/usr/bin/env python3
"""Florida Venue Ingestion using Overpass API (OpenStreetMap)"""

import sqlite3
import requests
import time
import json
from datetime import datetime
from typing import List, Dict, Tuple
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

DB_PATH = '/var/www/html/minerva/data/neutraleats.db'
FLORIDA_BOUNDS = {'lat_min': 24.0, 'lat_max': 31.0, 'lng_min': -88.0, 'lng_max': -79.0}

# Key areas - split into batches
BATCH_1_ORLANDO = [
    ('Lake Mary, FL', 28.7589, -81.3178), ('Longwood, FL', 28.7031, -81.3384),
    ('Altamonte Springs, FL', 28.6611, -81.3656), ('Maitland, FL', 28.6278, -81.3631),
    ('Winter Park, FL', 28.5986, -81.3512), ('Oviedo, FL', 28.6700, -81.2081),
    ('Ocoee, FL', 28.5692, -81.5440), ('Windermere, FL', 28.4956, -81.5348),
    ('Winter Garden, FL', 28.5653, -81.5862), ('Kissimmee, FL', 28.2920, -81.4076),
]

BATCH_2_TAMPA = [
    ('Riverview, FL', 27.8661, -82.3265), ('Brandon, FL', 27.9378, -82.2859),
    ('Clearwater, FL', 27.9659, -82.8001), ('St Pete Beach, FL', 27.7253, -82.7412),
    ('Seminole, FL', 27.8406, -82.7912), ('Palm Harbor, FL', 28.0781, -82.7637),
]

BATCH_3_MIAMI = [
    ('Miami Beach, FL', 25.7907, -80.1300), ('Aventura, FL', 25.9565, -80.1392),
    ('Coral Springs, FL', 26.2712, -80.2706), ('Hollywood, FL', 26.0112, -80.1495),
    ('Fort Lauderdale, FL', 26.1224, -80.1373), ('Boca Raton, FL', 26.3587, -80.0831),
]

BATCH_4_MAJOR = [
    ('Lakeland, FL', 28.0395, -81.9498), ('Gainesville, FL', 29.6516, -82.3248),
    ('Pensacola, FL', 30.4213, -87.2169), ('Jacksonville, FL', 30.3322, -81.6557),
    ('Tallahassee, FL', 30.4383, -84.2807), ('Naples, FL', 26.1420, -81.7948),
    ('Sarasota, FL', 27.3364, -82.5307), ('Daytona Beach, FL', 29.2108, -81.0228),
    ('Fort Myers, FL', 26.6406, -81.8723), ('Melbourne, FL', 28.0836, -80.6081),
]

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def fetch_restaurants(lat: float, lng: float, radius: int = 3000) -> List[Dict]:
    query = f"""[out:json][timeout:25];(node["amenity"~"restaurant|fast_food|cafe"](around:{radius},{lat},{lng});way["amenity"~"restaurant|fast_food|cafe"](around:{radius},{lat},{lng}););out center;"""
    
    try:
        resp = requests.post("https://overpass-api.de/api/interpreter", data={'data': query}, timeout=30)
        data = resp.json()
        venues = []
        for el in data.get('elements', []):
            if el['type'] == 'node':
                venues.append({'id': f"osm_{el['id']}", 'name': el.get('tags', {}).get('name', 'Restaurant'),
                    'lat': el.get('lat'), 'lng': el.get('lon'), 'type': el.get('tags', {}).get('amenity', 'restaurant')})
            elif el['type'] == 'way' and 'center' in el:
                venues.append({'id': f"osm_{el['id']}", 'name': el.get('tags', {}).get('name', 'Restaurant'),
                    'lat': el['center']['lat'], 'lng': el['center']['lon'], 'type': el.get('tags', {}).get('amenity', 'restaurant')})
        return venues
    except Exception as e:
        logger.error(f"Fetch error: {e}")
        return []

def save_venues(venues: List[Dict]) -> int:
    conn = get_db()
    cursor = conn.cursor()
    new_count = 0
    ts = int(time.time())
    
    for v in venues:
        lat, lng = v['lat'], v['lng']
        if not lat or not lng: continue
        if (lat < FLORIDA_BOUNDS['lat_min'] or lat > FLORIDA_BOUNDS['lat_max'] or
            lng < FLORIDA_BOUNDS['lng_min'] or lng > FLORIDA_BOUNDS['lng_max']): continue
        if 'london' in v['name'].lower() or 'uk' in v['name'].lower(): continue
        
        cursor.execute("SELECT 1 FROM venues WHERE id=?", (v['id'],))
        if not cursor.fetchone():
            new_count += 1
            cursor.execute("INSERT INTO venues (id, name, lat, lng, type, source, source_id, last_updated, first_seen, check_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)",
                (v['id'], v['name'], lat, lng, v['type'], 'openstreetmap', v['id'], ts, ts))
    
    conn.commit()
    conn.close()
    return new_count

def ingest_batch(batch_name: str, areas: List[Tuple]) -> int:
    logger.info(f"\n=== {batch_name} ===")
    total_new = 0
    for name, lat, lng in areas:
        venues = fetch_restaurants(lat, lng)
        new = save_venues(venues)
        total_new += new
        logger.info(f"{name}: {len(venues)} found, {new} new")
        time.sleep(3)
    return total_new

def main():
    logger.info("FLORIDA VENUE INGESTION - OVERPASS API")
    conn = get_db()
    start_count = conn.execute("SELECT COUNT(*) FROM venues").fetchone()[0]
    conn.close()
    logger.info(f"Starting with {start_count} venues")
    
    total = 0
    total += ingest_batch("BATCH 1: Orlando Metro", BATCH_1_ORLANDO)
    total += ingest_batch("BATCH 2: Tampa Bay", BATCH_2_TAMPA)
    total += ingest_batch("BATCH 3: Miami/FLL", BATCH_3_MIAMI)
    total += ingest_batch("BATCH 4: Major Cities", BATCH_4_MAJOR)
    
    conn = get_db()
    end_count = conn.execute("SELECT COUNT(*) FROM venues").fetchone()[0]
    conn.close()
    
    logger.info(f"\nCOMPLETE: Started with {start_count}, ended with {end_count}, added {end_count - start_count}")

if __name__ == '__main__':
    main()
