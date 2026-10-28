#!/usr/bin/env python3
"""
Florida Comprehensive Venue Ingestion for Neutral Eats
Target: 8,000+ clean venues across all Florida cities and suburbs
"""

import sqlite3
import requests
import time
import json
from datetime import datetime
from typing import List, Dict, Tuple
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('florida_full_ingest.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Database path
DB_PATH = '/var/www/html/minerva/data/neutraleats.db'

# Florida bounding box
FLORIDA_BOUNDS = {
    'lat_min': 24.0,
    'lat_max': 31.0,
    'lng_min': -88.0,
    'lng_max': -79.0
}

# Google Places API Key
API_KEY = 'REDACTED'

# Phase 1: Orlando Metro + Missing Suburbs
PHASE_1_AREAS = [
    ('Lake Mary, FL', 28.7589, -81.3178),
    ('Longwood, FL', 28.7031, -81.3384),
    ('Altamonte Springs, FL', 28.6611, -81.3656),
    ('Maitland, FL', 28.6278, -81.3631),
    ('Winter Park, FL', 28.5986, -81.3512),
    ('Oviedo, FL', 28.6700, -81.2081),
    ('Ocoee, FL', 28.5692, -81.5440),
    ('Windermere, FL', 28.4956, -81.5348),
    ('Winter Garden, FL', 28.5653, -81.5862),
    ('Dr Phillips, FL', 28.4514, -81.4923),
    ('Bay Hill, FL', 28.4619, -81.5162),
    ('Avalon Park, FL', 28.5489, -81.1545),
    ('Lake Nona, FL', 28.3569, -81.2806),
    ('Hunters Creek, FL', 28.3606, -81.4270),
    ('Kissimmee, FL', 28.2920, -81.4076),
    ('St Cloud, FL', 28.2489, -81.2812),
    ('Celebration, FL', 28.3152, -81.5476),
]

# Phase 2: Tampa Bay Suburbs
PHASE_2_AREAS = [
    ('Riverview, FL', 27.8661, -82.3265),
    ('Brandon, FL', 27.9378, -82.2859),
    ('Valrico, FL', 27.9375, -82.2364),
    ('Wesley Chapel, FL', 28.2397, -82.3279),
    ('Land O Lakes, FL', 28.2189, -82.4576),
    ('Lutz, FL', 28.1511, -82.4615),
    ('Clearwater, FL', 27.9659, -82.8001),
    ('Palm Harbor, FL', 28.0781, -82.7637),
    ('Dunedin, FL', 28.0197, -82.7718),
    ('St Pete Beach, FL', 27.7253, -82.7412),
    ('Gulfport, FL', 27.7484, -82.7034),
    ('Seminole, FL', 27.8406, -82.7912),
    ('Pinellas Park, FL', 27.8428, -82.6995),
]

# Phase 3: Miami/FLL Suburbs
PHASE_3_AREAS = [
    ('Miami Beach, FL', 25.7907, -80.1300),
    ('Aventura, FL', 25.9565, -80.1392),
    ('Sunny Isles Beach, FL', 25.9429, -80.1200),
    ('North Miami, FL', 25.8901, -80.1867),
    ('Coral Springs, FL', 26.2712, -80.2706),
    ('Miramar, FL', 25.9861, -80.3036),
    ('Weston, FL', 26.1004, -80.3998),
    ('Pembroke Pines, FL', 26.0078, -80.2963),
    ('Plantation, FL', 26.1276, -80.2331),
    ('Sunrise, FL', 26.1443, -80.2656),
    ('Delray Beach, FL', 26.4615, -80.0728),
    ('Boynton Beach, FL', 26.5253, -80.0664),
    ('Boca Raton, FL', 26.3587, -80.0831),
]

# Phase 4: Major Cities
PHASE_4_AREAS = [
    ('Lakeland, FL', 28.0395, -81.9498),
    ('Gainesville, FL', 29.6516, -82.3248),
    ('Pensacola, FL', 30.4213, -87.2169),
    ('Cape Coral, FL', 26.5629, -81.9495),
    ('Fort Myers, FL', 26.6406, -81.8723),
    ('Naples, FL', 26.1420, -81.7948),
    ('Sarasota, FL', 27.3364, -82.5307),
    ('Bradenton, FL', 27.4989, -82.5748),
    ('Melbourne, FL', 28.0836, -80.6081),
    ('Palm Bay, FL', 28.0345, -80.5887),
    ('Titusville, FL', 28.6122, -80.8076),
    ('Cocoa, FL', 28.3861, -80.7420),
    ('Daytona Beach, FL', 29.2108, -81.0228),
    ('Port St Lucie, FL', 27.2730, -80.3582),
    ('Vero Beach, FL', 27.6386, -80.3973),
    ('Key West, FL', 24.5551, -81.7800),
    ('St Augustine, FL', 29.9012, -81.3124),
]

# Phase 5: Everything Else - Additional suburbs and small towns
PHASE_5_AREAS = [
    ('Jacksonville Beach, FL', 30.2841, -81.3961),
    ('Ponte Vedra Beach, FL', 30.2397, -81.3856),
    ('Orange Park, FL', 30.1661, -81.7065),
    ('Fleming Island, FL', 30.0933, -81.7187),
    ('Atlantic Beach, FL', 30.3344, -81.3987),
    ('Neptune Beach, FL', 30.3244, -81.4009),
    ('Tallahassee, FL', 30.4383, -84.2807),
    ('Alachua, FL', 29.7516, -82.4248),
    ('Newberry, FL', 29.6464, -82.6065),
    ('Ocala, FL', 29.1872, -82.1401),
    ('The Villages, FL', 28.9342, -81.9687),
    ('Temple Terrace, FL', 28.0353, -82.3893),
    ('Plant City, FL', 28.0186, -82.1129),
    ('Venice, FL', 27.0998, -82.4543),
    ('North Port, FL', 27.0442, -82.2359),
    ('Englewood, FL', 26.9620, -82.3526),
    ('Bonita Springs, FL', 26.3398, -81.7787),
    ('Estero, FL', 26.4359, -81.8068),
    ('Lehigh Acres, FL', 26.6254, -81.6248),
    ('Stuart, FL', 27.1975, -80.2528),
    ('Jensen Beach, FL', 27.2544, -80.2298),
    ('Fort Pierce, FL', 27.4467, -80.3256),
    ('Satellite Beach, FL', 28.1761, -80.5901),
    ('Indian Harbour Beach, FL', 28.1489, -80.5884),
    ('Rockledge, FL', 28.3508, -80.7255),
    ('Jupiter, FL', 26.9342, -80.0942),
    ('Palm Beach Gardens, FL', 26.8484, -80.1384),
    ('Wellington, FL', 26.6618, -80.2684),
    ('Royal Palm Beach, FL', 26.7084, -80.2306),
    ('Greenacres, FL', 26.6276, -80.1353),
    ('Lake Worth, FL', 26.6168, -80.0570),
    ('Lantana, FL', 26.5867, -80.0514),
    ('Parkland, FL', 26.3101, -80.2373),
    ('Tamarac, FL', 26.2129, -80.2498),
    ('Margate, FL', 26.2445, -80.2064),
    ('Lauderhill, FL', 26.1404, -80.2134),
    ('Davie, FL', 26.0765, -80.2521),
    ('Cooper City, FL', 26.0573, -80.2717),
    ('Hallandale Beach, FL', 25.9812, -80.1484),
    ('Hollywood, FL', 26.0112, -80.1495),
    ('Dania Beach, FL', 26.0523, -80.1439),
    ('Fort Lauderdale, FL', 26.1224, -80.1373),
    ('Oakland Park, FL', 26.1723, -80.1319),
    ('Pompano Beach, FL', 26.2379, -80.1248),
    ('Deerfield Beach, FL', 26.3184, -80.0998),
    ('Miami Lakes, FL', 25.9087, -80.3087),
    ('Hialeah, FL', 25.8576, -80.2781),
    ('Doral, FL', 25.8195, -80.3553),
    ('Coral Gables, FL', 25.7215, -80.2684),
    ('Pinecrest, FL', 25.6660, -80.3081),
    ('Homestead, FL', 25.4687, -80.4776),
    ('Apopka, FL', 28.6761, -81.5115),
    ('Casselberry, FL', 28.6775, -81.3278),
    ('Winter Springs, FL', 28.6989, -81.3081),
    ('Sanford, FL', 28.8029, -81.2695),
    ('DeLand, FL', 29.0283, -81.3031),
    ('Mount Dora, FL', 28.8025, -81.6445),
    ('Leesburg, FL', 28.8108, -81.8779),
    ('Clermont, FL', 28.5494, -81.7729),
    ('Panama City, FL', 30.1588, -85.6602),
    ('Panama City Beach, FL', 30.1766, -85.8055),
    ('Destin, FL', 30.3935, -86.4958),
    ('Fort Walton Beach, FL', 30.4058, -86.6188),
    ('Jacksonville, FL', 30.3322, -81.6557),
    ('St Johns, FL', 30.0822, -81.5473),
    ('Lake City, FL', 30.1897, -82.6393),
    ('Sebring, FL', 27.4956, -81.4409),
    ('Wauchula, FL', 27.5473, -81.8115),
    ('Arcadia, FL', 27.2159, -81.8584),
    ('Okeechobee, FL', 27.2439, -80.8298),
    ('Punta Gorda, FL', 26.9298, -82.0454),
    ('Port Charlotte, FL', 26.9762, -82.0906),
    ('Marco Island, FL', 25.9390, -81.7076),
    ('Clewiston, FL', 26.7542, -80.9337),
    ('Stuart, FL', 27.1975, -80.2528),
    ('Vero Beach, FL', 27.6386, -80.3973),
    ('Sebastian, FL', 27.8164, -80.4706),
    ('Cocoa Beach, FL', 28.3200, -80.6096),
    ('Cape Canaveral, FL', 28.3922, -80.6077),
    ('New Smyrna Beach, FL', 29.0258, -80.9270),
    ('Ormond Beach, FL', 29.2858, -81.0559),
    ('Palm Coast, FL', 29.5850, -81.2078),
]

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def generate_grid_cell(lat: float, lng: float) -> str:
    # Canonical venues.grid_cell (pipeline/merge_overture.py)
    import math
    return "%.3f,%.3f" % (math.floor(lat / 0.02) * 0.02, math.floor(lng / 0.02) * 0.02)

def fetch_places_near(lat: float, lng: float, radius: int = 2500, keyword: str = None) -> List[Dict]:
    url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    params = {
        'location': f'{lat},{lng}',
        'radius': radius,
        'type': 'restaurant',
        'key': API_KEY
    }
    
    if keyword:
        params['keyword'] = keyword
    
    venues = []
    next_page_token = None
    
    try:
        for page in range(3):
            if next_page_token:
                params['pagetoken'] = next_page_token
            
            response = requests.get(url, params=params, timeout=30)
            data = response.json()
            
            if data.get('status') not in ['OK', 'ZERO_RESULTS']:
                logger.warning(f"API error: {data.get('status')}")
                break
            
            results = data.get('results', [])
            for place in results:
                venue = {
                    'id': place['place_id'],
                    'name': place['name'],
                    'lat': place['geometry']['location']['lat'],
                    'lng': place['geometry']['location']['lng'],
                    'types': place.get('types', []),
                    'vicinity': place.get('vicinity', ''),
                }
                venues.append(venue)
            
            next_page_token = data.get('next_page_token')
            if not next_page_token:
                break
            
            time.sleep(2)
    except Exception as e:
        logger.error(f"Error fetching places: {e}")
    
    return venues

def save_venues(venues: List[Dict], grid_cell: str) -> Tuple[int, int]:
    conn = get_db_connection()
    cursor = conn.cursor()
    
    new_count = 0
    existing_count = 0
    timestamp = int(time.time())
    
    for venue in venues:
        lat = venue['lat']
        lng = venue['lng']
        
        if (lat < FLORIDA_BOUNDS['lat_min'] or lat > FLORIDA_BOUNDS['lat_max'] or
            lng < FLORIDA_BOUNDS['lng_min'] or lng > FLORIDA_BOUNDS['lng_max']):
            continue
        
        cursor.execute("SELECT id FROM venues WHERE id = ?", (venue['id'],))
        if cursor.fetchone():
            existing_count += 1
            cursor.execute("UPDATE venues SET check_count = check_count + 1, last_updated = ? WHERE id = ?",
                          (timestamp, venue['id']))
        else:
            new_count += 1
            cursor.execute("""
                INSERT INTO venues (id, name, lat, lng, type, source, source_id, 
                                   last_updated, first_seen, grid_cell, check_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """, (venue['id'], venue['name'], lat, lng, ','.join(venue.get('types', [])),
                  'google_places', venue['id'], timestamp, timestamp, grid_cell))
    
    conn.commit()
    conn.close()
    return new_count, existing_count

def update_grid_cell(cell_key: str, lat: float, lng: float, venue_count: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    timestamp = int(time.time())
    next_fetch = timestamp + (7 * 24 * 3600)
    
    cursor.execute("""
        INSERT OR REPLACE INTO grid_cells 
        (cell_key, lat_min, lat_max, lng_min, lng_max, venue_count, last_fetched, next_fetch)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (cell_key, lat - 0.025, lat + 0.025, lng - 0.025, lng + 0.025, venue_count, timestamp, next_fetch))
    
    conn.commit()
    conn.close()

def ingest_area(area_name: str, lat: float, lng: float, radius: int = 2500) -> Dict:
    logger.info(f"Ingesting: {area_name}")
    
    all_venues = []
    keywords = ['restaurant', 'cafe', 'fast food', 'diner']
    
    for keyword in keywords:
        venues = fetch_places_near(lat, lng, radius, keyword)
        all_venues.extend(venues)
        time.sleep(1)
    
    seen_ids = set()
    unique_venues = []
    for v in all_venues:
        if v['id'] not in seen_ids:
            seen_ids.add(v['id'])
            unique_venues.append(v)
    
    grid_cell = generate_grid_cell(lat, lng)
    new_count, existing_count = save_venues(unique_venues, grid_cell)
    update_grid_cell(grid_cell, lat, lng, len(unique_venues))
    
    result = {
        'area': area_name,
        'venues_found': len(unique_venues),
        'new_venues': new_count,
    }
    
    logger.info(f"  -> Found: {len(unique_venues)}, New: {new_count}")
    return result

def run_phase(phase_name: str, areas: List[Tuple], radius: int = 2500) -> Dict:
    logger.info(f"\n{'='*60}")
    logger.info(f"STARTING {phase_name}")
    logger.info(f"{'='*60}")
    
    results = []
    total_new = 0
    
    for area_name, lat, lng in areas:
        try:
            result = ingest_area(area_name, lat, lng, radius)
            results.append(result)
            total_new += result['new_venues']
            time.sleep(1)
        except Exception as e:
            logger.error(f"Error processing {area_name}: {e}")
    
    summary = {
        'phase': phase_name,
        'areas_processed': len(areas),
        'total_new_venues': total_new,
    }
    
    logger.info(f"\n{phase_name} COMPLETE: {len(areas)} areas, {total_new} new venues")
    return summary

def get_db_stats():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM venues")
    total_venues = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM grid_cells")
    total_cells = cursor.fetchone()[0]
    conn.close()
    return {'total_venues': total_venues, 'total_cells': total_cells}

def main():
    logger.info("="*60)
    logger.info("FLORIDA COMPREHENSIVE VENUE INGESTION")
    logger.info("="*60)
    
    stats_before = get_db_stats()
    logger.info(f"Starting: {stats_before['total_venues']} venues, {stats_before['total_cells']} cells")
    
    all_summaries = []
    phases = [
        ("PHASE 1: Orlando Metro", PHASE_1_AREAS),
        ("PHASE 2: Tampa Bay", PHASE_2_AREAS),
        ("PHASE 3: Miami/FLL", PHASE_3_AREAS),
        ("PHASE 4: Major Cities", PHASE_4_AREAS),
        ("PHASE 5: Additional Areas", PHASE_5_AREAS),
    ]
    
    for phase_name, areas in phases:
        summary = run_phase(phase_name, areas, radius=2500)
        all_summaries.append(summary)
        stats = get_db_stats()
        logger.info(f"[Checkpoint] Total: {stats['total_venues']} venues")
    
    stats_after = get_db_stats()
    logger.info("\n" + "="*60)
    logger.info("FINAL SUMMARY")
    logger.info("="*60)
    logger.info(f"Before: {stats_before['total_venues']} venues")
    logger.info(f"After: {stats_after['total_venues']} venues")
    logger.info(f"Added: {stats_after['total_venues'] - stats_before['total_venues']} venues")
    
    report = {
        'timestamp': datetime.now().isoformat(),
        'before': stats_before,
        'after': stats_after,
        'phases': all_summaries
    }
    with open('florida_ingest_report.json', 'w') as f:
        json.dump(report, f, indent=2)

if __name__ == '__main__':
    main()
