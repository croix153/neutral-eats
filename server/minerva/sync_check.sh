#!/bin/bash
# Database Sync Diagnostic for Neutral Eats

echo "🔍 DATABASE SYNC DIAGNOSTIC"
echo "=============================="
echo ""

# Check venue counts by source
echo "📊 Venues by source:"
mysql -u neutraleats_user -pneutraleats_pass neutraleats -e "
    SELECT source, COUNT(*) as count, 
           COUNT(DISTINCT SUBSTRING(address, -5)) as zip_codes,
           ROUND(AVG(rating), 2) as avg_rating
    FROM venues 
    GROUP BY source 
    ORDER BY count DESC;
" 2>/dev/null

echo ""
echo "📍 Geographic coverage:"
mysql -u neutraleats_user -pneutraleats_pass neutraleats -e "
    SELECT 
        CASE 
            WHEN address LIKE '%FL%' THEN 'Florida'
            WHEN address LIKE '%CA%' THEN 'California'
            WHEN address LIKE '%TX%' THEN 'Texas'
            WHEN address LIKE '%NY%' THEN 'New York'
            WHEN address LIKE '%IL%' THEN 'Illinois'
            ELSE 'Other'
        END as state,
        COUNT(*) as count
    FROM venues 
    WHERE address IS NOT NULL
    GROUP BY state 
    ORDER BY count DESC;
" 2>/dev/null

echo ""
echo "🔍 Potential issues:"
mysql -u neutraleats_user -pneutraleats_pass neutraleats -e "
    SELECT 
        'Inactive venues' as issue, 
        COUNT(*) as count 
    FROM venues 
    WHERE is_active = 0
    UNION ALL
    SELECT 
        'Missing coordinates',
        COUNT(*)
    FROM venues
    WHERE lat IS NULL OR lng IS NULL
    UNION ALL
    SELECT 
        'Missing source_id',
        COUNT(*)
    FROM venues  
    WHERE source_id IS NULL OR source_id = '';
" 2>/dev/null

echo ""
echo "🗺️  Grid cell coverage:"
mysql -u neutraleats_user -pneutraleats_pass neutraleats -e "
    SELECT 
        COUNT(*) as total_cells,
        SUM(venue_count) as tracked_venues,
        AVG(venue_count) as avg_per_cell,
        MAX(venue_count) as max_in_cell
    FROM grid_cells;
" 2>/dev/null

echo ""
echo "📝 Recent ingestion activity:"
tail -5 /var/www/html/minerva/data/aggressive_ingestion.log 2>/dev/null | grep -E 'Processing|Done|new' || echo "No recent activity"

echo ""
echo "=============================="
echo "To fix sync issues:"
echo "1. Run: python3 /var/www/html/minerva/aggressive_ingestion.py"
echo "2. Check grid_cells vs venues gap"
echo "3. Verify all sources are writing correctly"
