#!/usr/bin/env python3
"""
Lake Mary FL Yelp Enrichment for Neutral Eats
"""
import requests
import json
import time

YELP_API_KEY = 'REDACTED'

# Lake Mary search areas
AREAS = [
    {"name": "Lake Mary Center", "lat": 28.7589, "lng": -81.3178, "radius": 2000},
    {"name": "Heathrow", "lat": 28.7750, "lng": -81.3400, "radius": 2500},
    {"name": "Colonial TownPark", "lat": 28.7450, "lng": -81.3100, "radius": 1500},
    {"name": "Lake Mary Blvd", "lat": 28.7550, "lng": -81.3300, "radius": 2000},
    {"name": "Rinehart Rd", "lat": 28.7600, "lng": -81.3500, "radius": 1500},
]

def fetch_yelp(lat, lng, radius=2000, offset=0):
    """Fetch restaurants from Yelp"""
    url = "https://api.yelp.com/v3/businesses/search"
    headers = {"Authorization": f"Bearer {YELP_API_KEY}"}
    params = {
        "latitude": lat,
        "longitude": lng,
        "radius": radius,
        "categories": "restaurants,food,cafes,bars",
        "limit": 50,
        "offset": offset,
        "sort_by": "best_match"
    }
    
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        if resp.status_code == 200:
            return resp.json().get('businesses', [])
        else:
            print(f"  Error: HTTP {resp.status_code}")
            return []
    except Exception as e:
        print(f"  Error: {e}")
        return []

def main():
    print("🍽️ Lake Mary Yelp Data Collection")
    print("=" * 60)
    
    all_venues = []
    
    for area in AREAS:
        print(f"\n🔍 {area['name']}...")
        
        for offset in [0, 50]:  # Get up to 100 per area
            venues = fetch_yelp(area['lat'], area['lng'], area['radius'], offset)
            
            for v in venues:
                venue_data = {
                    'name': v.get('name'),
                    'lat': v.get('coordinates', {}).get('latitude'),
                    'lng': v.get('coordinates', {}).get('longitude'),
                    'type': v.get('categories', [{}])[0].get('title', 'restaurant'),
                    'cuisine': ', '.join([c.get('title', '') for c in v.get('categories', [])]),
                    'rating': v.get('rating'),
                    'price': v.get('price'),
                    'address': ' '.join(v.get('location', {}).get('display_address', [])),
                    'city': v.get('location', {}).get('city'),
                    'state': v.get('location', {}).get('state'),
                    'zip': v.get('location', {}).get('zip_code'),
                    'phone': v.get('phone'),
                    'yelp_id': v.get('id'),
                    'url': v.get('url'),
                    'source': 'yelp'
                }
                all_venues.append(venue_data)
            
            print(f"  Offset {offset}: {len(venues)} venues")
            time.sleep(0.5)  # Rate limiting
    
    # Save to file for review
    output_file = '/root/.openclaw/workspace/lake_mary_yelp_data.json'
    with open(output_file, 'w') as f:
        json.dump(all_venues, f, indent=2)
    
    print(f"\n✅ Collected {len(all_venues)} venues")
    print(f"📁 Saved to: {output_file}")
    
    # Show sample
    print("\n📝 Sample venues:")
    for v in all_venues[:5]:
        print(f"  - {v['name']} ({v['type']}) - {v['address'][:50]}...")

if __name__ == "__main__":
    main()
