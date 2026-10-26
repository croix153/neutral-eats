#!/usr/bin/env python3
"""
Database Sync Repair for Neutral Eats
Finds and syncs missing venues from grid_cells tracking
"""

import mysql.connector
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/www/html/minerva/data/sync_repair.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

DB_CONFIG = {
    'host': 'localhost',
    'user': 'neutraleats_user',
    'password': 'REDACTED',
    'database': 'neutraleats'
}

def get_db():
    return mysql.connector.connect(**DB_CONFIG)

def check_sync_status():
    """Check current sync status"""
    db = get_db()
    cursor = db.cursor()
    
    # Get counts
    cursor.execute("SELECT SUM(venue_count) FROM grid_cells")
    tracked = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT COUNT(*) FROM venues")
    actual = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT COUNT(*) FROM pending_updates")
    pending = cursor.fetchone()[0] or 0
    
    logger.info(f"Sync Status: Tracked={tracked}, Actual={actual}, Pending={pending}, Gap={tracked - actual}")
    
    cursor.close()
    db.close()
    return tracked, actual, pending

def find_missing_venues():
    """Find venues in grid_cells that aren't in venues table"""
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    # Check for venues that might be referenced but not exist
    cursor.execute("SELECT COUNT(*) FROM venues WHERE source_id IS NULL OR source_id = ''")
    missing_source = cursor.fetchone()['COUNT(*)']
    logger.info(f"Venues with missing source_id: {missing_source}")
    
    # Check inactive venues
    cursor.execute("SELECT COUNT(*) FROM venues WHERE is_active = 0")
    inactive = cursor.fetchone()['COUNT(*)']
    logger.info(f"Inactive venues: {inactive}")
    
    # Check venue distribution by grid
    cursor.execute("SELECT cell_key, venue_count FROM grid_cells WHERE venue_count > 0 ORDER BY venue_count DESC LIMIT 10")
    top_cells = cursor.fetchall()
    logger.info(f"Top 10 grid cells by tracked count:")
    for cell in top_cells:
        # Count actual venues in this area
        cursor.execute("""
            SELECT COUNT(*) FROM venues 
            WHERE lat BETWEEN %s AND %s AND lng BETWEEN %s AND %s
        """, (cell['lat_min'], cell['lat_max'], cell['lng_min'], cell['lng_max']))
        actual = cursor.fetchone()['COUNT(*)']
        gap = cell['venue_count'] - actual
        if gap > 0:
            logger.info(f"  {cell['cell_key']}: tracked={cell['venue_count']}, actual={actual}, gap={gap}")
    
    cursor.close()
    db.close()
    return missing_source, inactive

def verify_integrity():
    """Check database integrity"""
    db = get_db()
    cursor = db.cursor()
    
    # Check for duplicate source_ids
    cursor.execute("""
        SELECT source_id, COUNT(*) as cnt 
        FROM venues 
        WHERE source_id IS NOT NULL AND source_id != ''
        GROUP BY source_id 
        HAVING cnt > 1
    """)
    dups = cursor.fetchall()
    if dups:
        logger.warning(f"Found {len(dups)} duplicate source_ids")
    else:
        logger.info("No duplicate source_ids found")
    
    # Check for venues without coordinates
    cursor.execute("SELECT COUNT(*) FROM venues WHERE lat IS NULL OR lng IS NULL")
    no_coords = cursor.fetchone()[0]
    if no_coords > 0:
        logger.warning(f"Found {no_coords} venues without coordinates")
    else:
        logger.info("All venues have coordinates")
    
    # Check source distribution
    cursor.execute("SELECT source, COUNT(*) FROM venues GROUP BY source ORDER BY COUNT(*) DESC")
    sources = cursor.fetchall()
    logger.info("Venues by source:")
    for src, cnt in sources:
        logger.info(f"  {src}: {cnt}")
    
    cursor.close()
    db.close()
    return len(dups), no_coords

def main():
    logger.info("="*70)
    logger.info("DATABASE SYNC REPAIR STARTED")
    logger.info("="*70)
    
    tracked, actual, pending = check_sync_status()
    missing_source, inactive = find_missing_venues()
    dups, no_coords = verify_integrity()
    
    logger.info("="*70)
    logger.info("SYNC STATUS SUMMARY")
    logger.info("="*70)
    logger.info(f"Grid cells tracking: {tracked:,} venues")
    logger.info(f"Actual in venues table: {actual:,} venues")
    logger.info(f"Gap: {tracked - actual:,} venues")
    logger.info(f"Inactive venues: {inactive}")
    logger.info(f"Duplicate source_ids: {dups}")
    logger.info(f"Venues without coordinates: {no_coords}")
    logger.info("="*70)
    
    if tracked > actual:
        logger.info("\n⚠️  SYNC GAP DETECTED!")
        logger.info(f"   {tracked - actual:,} venues tracked but not in main table")
        logger.info("\nRecommended actions:")
        logger.info("1. Re-run ingestion for grid cells with gaps")
        logger.info("2. Check if venues are marked inactive when they should be active")
        logger.info("3. Verify ingestion pipeline is writing to correct table")
    else:
        logger.info("\n✅ Database is in sync")

if __name__ == "__main__":
    main()
