#!/usr/bin/env python3
"""
Neutral Eats - Lake Mary FL Yelp Enrichment
Targeted script to bulk up Lake Mary restaurant coverage
"""

import requests
import mysql.connector
import time
import json
from datetime import datetime
from typing import List, Dict

# Database config
DB_CONFIG = {
    'host': 'localhost',
    'user': 'neutraleats_user',
    'password': 'REDACTED',
    'database': 'neutraleats'
}

# Yelp API Key - will be set via environment or parameter
YELP_API_KEY = None

# Lake Mary, FL boundaries (approximate)
LAKE_MARY_BOUNDS = {
    'lat_min': 28.7300,
    'lat_max': 28.7800,
    'lng_min': -81.3600,
    'lng_max': -81.3000,
    'center_lat': 28.7589,
    'center_lng': -81.3178
}

# Target neighborhoods/areas within Lake Mary
LAKE_MARY_AREAS = [
    {"name": "Lake Mary Center", "lat": 28.7589, "lng": -81.3178, "radius": 2000},
    {"name": "Heathrow", "lat": 28.7750, "lng": -81.3400, "radius": 2500},
    {"name": "Colonial TownPark", "lat": 28.7450, "lng": -81.3100, "radius": 1500},
    {"name": "Lake Mary Blvd", "lat": 28.7550, "lng": -81.3300, "radius": 2000},
    {"name": "Rinehart Rd", "lat": 28.7600, "lng": -81.3500, "radius": 1500},
]

def get_db_connection():
    """Get MySQL connection"""
    try:
        return mysql.connector.connect(**DB_CONFIG)
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return None

def check_lake_mary_coverage():
    """Check current venue count in Lake Mary area"""
    conn = get_db_connection()
    if not conn:
        return 0
    
    cursor = conn.cursor()
    
    # Check total venues in Lake Mary bounds
    query = """
        SELECT COUNT(*) FROM venues 
        WHERE lat BETWEEN %s AND %s 
        AND lng BETWEEN %s AND %s
    """
    cursor.execute(query, (
        LAKE_MARY_BOUNDS['lat_min'],
        LAKE_MARY_BOUNDS['lat_max'],
        LAKE_MARY_BOUNDS['lng_min'],
        LAKE_MARY_BOUNDS['lng_max']
    ))
    total_count = cursor.fetchone()[0]
    
    # Check by source
    query = """
        SELECT source, COUNT(*) FROM venues 
        WHERE lat BETWEEN %s AND %s 
        AND lng BETWEEN %s AND %s
        GROUP BY source
    """
    cursor.execute(query, (
        LAKE_MARY_BOUNDS['lat_min'],
        LAKE_MARY_BOUNDS['lat_max'],
        LAKE_MARY_BOUNDS['lng_min'],
        LAKE_MARY_BOUNDS['lng_max']
    ))
    sources = cursor.fetchall()
    
    # Check with "Lake Mary" in address
    query = """
        SELECT COUNT(*) FROM venues 
        WHERE address LIKE '%Lake Mary%'
        OR city = 'Lake Mary'
    """
    cursor.execute(query)
    address_count = cursor.fetchone()[0]
    
    cursor.close()
    conn.close()
    
    print(f"\n📊 Lake Mary Coverage Report")
    print("="*50)
    print(f"Venues in bounds: {total_count}")
    print(f"Venues with 'Lake Mary' in address: {address_count}")
    print("\nBy source:")
    for source, count in sources:
        print(f"  - {source}: {count}")
    
    return total_count

def fetch_yelp_area(lat: float, lng: float, radius: int = 2000, offset: int = 0) -> List[Dict]:
    """Fetch restaurants from Yelp for a specific area"""
    if not YELP_API_KEY:
        print("❌ Yelp API key not set")
        return []
    
    url = "https://api.yelp.com/v3/businesses/search"
    headers = {"Authorization": f"Bearer {YELP_API_KEY}"}
    params = {
        "latitude": lat,
        "longitude": lng,
        "radius": radius,
        "categories": "restaurants,food,cafes,bars,pubs",
        "limit": 50,
        "offset": offset,
        "sort_by": "best_match"
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        venues = []
        for business in data.get('businesses', []):
            coords = business.get('coordinates', {})
            location = business.get('location', {})
            
            venue = {
                'name': business.get('name'),
                'lat': coords.get('latitude'),
                'lng': coords.get('longitude'),
                'type': categorize_type(business.get('categories', [{}])[0].get('title', '')),
                'cuisine': ', '.join([c.get('title', '') for c in business.get('categories', [])]),
                'brand': '',
                'rating': business.get('rating'),
                'price_level': len(business.get('price', '')),
                'address': ', '.join(location.get('display_address', [])),
                'city': location.get('city', ''),
                'state': location.get('state', ''),
                'zip': location.get('zip_code', ''),
                'phone': business.get('phone', ''),
                'website': business.get('url', ''),
                'source': 'yelp',
                'source_id': business.get('id'),
                'raw_data': business,
                'review_count': business.get('review_count', 0),
                'is_closed': business.get('is_closed', False)
            }
            venues.append(venue)
        
        return venues
        
    except Exception as e:
        print(f"❌ Yelp fetch failed: {e}")
        return []

def categorize_type(category_str: str) -> str:
    """Normalize category to restaurant/cafe/bar/pub"""
    cat = category_str.lower()
    if any(x in cat for x in ['cafe', 'coffee', 'bakery']):
        return 'cafe'
    elif any(x in cat for x in ['bar', 'pub', 'biergarten', 'wine']):
        return 'bar'
    elif any(x in cat for x in ['fast food', 'food court']):
        return 'fast_food'
    else:
        return 'restaurant'

def venue_exists(cursor, name: str, lat: float, lng: float) -> bool:
    """Check if venue already exists"""
    # Same name within 100m
    query = """
        SELECT id FROM venues 
        WHERE LOWER(name) = LOWER(%s)
        AND ABS(lat - %s) < 0.001 
        AND ABS(lng - %s) < 0.001
        LIMIT 1
    """
    cursor.execute(query, (name, lat, lng))
    return cursor.fetchone() is not None

def insert_venue(cursor, venue: Dict) -> bool:
    """Insert venue into database"""
    try:
        # Generate ID from source_id or hash
        venue_id = venue.get('source_id') or hash(f"{venue['name']}{venue['lat']}{venue['lng']}")
        
        query = """
            INSERT INTO venues (
                id, name, lat, lng, type, cuisine, brand, rating, price_level,
                address, city, state, zip, phone, website, source, source_id,
                is_active, last_updated, first_seen, check_count
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s,
                1, UNIX_TIMESTAMP(), UNIX_TIMESTAMP(), 1
            )
            ON DUPLICATE KEY UPDATE
                rating = VALUES(rating),
                price_level = VALUES(price_level),
                last_updated = UNIX_TIMESTAMP(),
                check_count = check_count + 1
        """
        cursor.execute(query, (
            venue_id,
            venue.get('name'),
            venue.get('lat'),
            venue.get('lng'),
            venue.get('type'),
            venue.get('cuisine'),
            venue.get('brand'),
            venue.get('rating'),
            venue.get('price_level'),
            venue.get('address'),
            venue.get('city'),
            venue.get('state'),
            venue.get('zip'),
            venue.get('phone'),
            venue.get('website'),
            venue.get('source'),
            venue.get('source_id')
        ))
        return True
    except Exception as e:
        print(f"❌ Insert failed: {e}")
        return False

def enrich_lake_mary():
    """Main enrichment function for Lake Mary"""
    global YELP_API_KEY
    
    print("\n🍽️  Neutral Eats - Lake Mary Yelp Enrichment")
    print("="*60)
    
    # Check current coverage
    before_count = check_lake_mary_coverage()
    
    # Get Yelp API key
    if not YELP_API_KEY:
        print("\n⚠️  Yelp API key needed")
        print("Get one at: https://www.yelp.com/developers/v3/manage_app")
        key = input("Enter Yelp API key (or press Enter to skip): ").strip()
        if key:
            YELP_API_KEY = key
        else:
            print("❌ No API key provided. Exiting.")
            return
    
    conn = get_db_connection()
    if not conn:
        return
    
    cursor = conn.cursor()
    total_added = 0
    total_skipped = 0
    
    print(f"\n🚀 Starting Yelp enrichment for Lake Mary...")
    print(f"📍 Areas to scan: {len(LAKE_MARY_AREAS)}")
    
    for area in LAKE_MARY_AREAS:
        print(f"\n🔍 Scanning: {area['name']} ({area['lat']}, {area['lng']})...")
        
        # Get up to 100 results per area (2 pages of 50)
        for offset in [0, 50]:
            venues = fetch_yelp_area(
                area['lat'], 
                area['lng'], 
                radius=area['radius'],
                offset=offset
            )
            
            added = 0
            skipped = 0
            
            for venue in venues:
                # Skip closed businesses
                if venue.get('is_closed'):
                    skipped += 1
                    continue
                
                # Check if already exists
                if venue_exists(cursor, venue['name'], venue['lat'], venue['lng']):
                    skipped += 1
                    continue
                
                # Insert new venue
                if insert_venue(cursor, venue):
                    added += 1
                    total_added += 1
                else:
                    skipped += 1
            
            total_skipped += skipped
            print(f"  Offset {offset}: +{added} new, {skipped} skipped")
            
            # Rate limiting - Yelp allows 5000/day, so ~1 call every 17 seconds
            # But we can go faster for small batches
            time.sleep(0.5)
    
    conn.commit()
    cursor.close()
    conn.close()
    
    print(f"\n✅ Lake Mary enrichment complete!")
    print(f"📈 Added: {total_added} new venues")
    print(f"🔄 Skipped (duplicates/closed): {total_skipped}")
    
    # Check coverage after
    print(f"\n📊 Before: {before_count} venues")
    after_count = check_lake_mary_coverage()
    print(f"📊 After: {after_count} venues")
    print(f"📊 Net gain: {after_count - before_count}")

def search_yelp_query(query: str, location: str = "Lake Mary, FL"):
    """Search Yelp with a specific query"""
    if not YELP_API_KEY:
        print("❌ Yelp API key not set")
        return []
    
    url = "https://api.yelp.com/v3/businesses/search"
    headers = {"Authorization": f"Bearer {YELP_API_KEY}"}
    params = {
        "term": query,
        "location": location,
        "categories": "restaurants,food",
        "limit": 50,
        "sort_by": "best_match"
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        return data.get('businesses', [])
    except Exception as e:
        print(f"❌ Yelp search failed: {e}")
        return []

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--check":
        # Just check coverage, don't add
        check_lake_mary_coverage()
    elif len(sys.argv) > 1 and sys.argv[1] == "--key":
        # Set API key from command line
        if len(sys.argv) > 2:
            YELP_API_KEY = sys.argv[2]
            enrich_lake_mary()
        else:
            print("Usage: python3 lake_mary_yelp.py --key <YELP_API_KEY>")
    else:
        # Interactive mode
        enrich_lake_mary()
