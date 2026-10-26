# Neutral Eats v2.0 - Deployment Guide

## Overview
Neutral Eats v2.0 adds comprehensive government and commercial data sources to dramatically expand restaurant coverage while maintaining local storage for fast performance.

## What's New

### Enhanced Data Sources
- **Government**: Florida DBPR, Orange County, Miami-Dade, other county health inspections
- **Federal**: USDA Farmers Market Directory, National Park Service concessions
- **Commercial**: Yelp, Google Places, Foursquare (for enrichment)
- **Open Data**: Overture Maps, OpenStreetMap

### New Features
- Multi-source merging with confidence scoring
- License number and inspection data tracking
- Grid-cell based spatial indexing
- Automated deduplication pipeline
- Data freshness tracking

## Deployment Steps

### 1. Database Upgrade

Run the schema upgrade on your MySQL server:

```bash
mysql -u neutraleats_user -p neutraleats < /var/www/html/minerva/neutraleats_schema_v2.sql
```

This will:
- Add new columns to existing tables
- Create new tables (source_metadata, duplicate_clusters, api_cache)
- Migrate existing data
- Set up indexes for performance

### 2. Upload New API Files

Deploy the new PHP scripts to your server:

```bash
# Copy all API files
scp minerva/api/*.php minerva@74.207.224.129:/var/www/html/minerva/api/

# Copy config
scp minerva/config/*.php minerva@74.207.224.129:/var/www/html/minerva/config/

# Create logs directory
ssh minerva@74.207.224.129 "mkdir -p /var/www/html/minerva/logs && chmod 755 /var/www/html/minerva/logs"
```

### 3. Configure Cron Jobs

Add these cron jobs for automated data ingestion:

```bash
# Edit crontab
crontab -e

# Add these lines:
# Run scheduler every 5 minutes
*/5 * * * * /usr/bin/php /var/www/html/minerva/api/sync_scheduler.php >> /var/www/html/minerva/logs/cron.log 2>&1

# Weekly full USDA farmers market refresh (Sundays at 2am)
0 2 * * 0 /usr/bin/php /var/www/html/minerva/api/ingest_usda_farmers_markets.php >> /var/www/html/minerva/logs/usda.log 2>&1

# Daily government data check (3am)
0 3 * * * /usr/bin/php /var/www/html/minerva/api/ingest_government_data.php >> /var/www/html/minerva/logs/gov.log 2>&1

# Daily deduplication (4am)
0 4 * * * /usr/bin/php /var/www/html/minerva/api/merge_enrich.php >> /var/www/html/minerva/logs/dedup.log 2>&1
```

### 4. Initial Data Population

Run initial ingestion to populate the database:

```bash
# 1. USDA Farmers Markets (nationwide, filters to FL)
php /var/www/html/minerva/api/ingest_usda_farmers_markets.php

# 2. Government data (requires manual steps, see below)
php /var/www/html/minerva/api/ingest_government_data.php

# 3. Deduplicate and merge
php /var/www/html/minerva/api/merge_enrich.php
```

### 5. Update Frontend (Optional)

To use the new v2 API with enhanced data, update your HTML:

```javascript
// In neutraleats2.html, change the API endpoint:
const CONFIG = {
    // ... other config
    API_BASE_URL: './api/venues_v2.php' // Use v2 endpoint
};
```

The v2 API returns richer data including:
- Government license numbers
- Inspection scores
- Source attribution
- Confidence scores
- Data freshness indicators

## Government Data Setup

### Florida DBPR Restaurant Licenses

1. Visit: https://www.myfloridalicense.com/DBPR/hr/search.html
2. Download restaurant license data as CSV
3. Place file at: `/var/www/html/minerva/data/dbpr_restaurants.csv`
4. Run: `php /var/www/html/minerva/api/ingest_government_data.php`

### Miami-Dade Restaurant Inspections

The script automatically fetches from their open data API. No setup required.

### Orange County Data

Orange County requires API key registration. Contact their open data team:
https://data.ocfl.net/

Once you have a key, add it to `config/database.php` or set as environment variable.

### Other Counties

The framework supports adding more county data sources. See `ingest_government_data.php` for examples and add new ingestion methods as needed.

## API Keys (Optional)

For commercial data enrichment, obtain API keys:

### Yelp Fusion
1. Create app at: https://www.yelp.com/developers/v3/manage_app
2. Add key to: `config/api_keys.php` (create this file)

### Google Places
1. Get API key: https://developers.google.com/maps/documentation/places/web-service/get-api-key
2. Enable Places API
3. Add key to: `config/api_keys.php`

### Foursquare
1. Create app: https://foursquare.com/developers/apps
2. Add client ID and secret to: `config/api_keys.php`

## Monitoring

### Check Logs

```bash
# Real-time log monitoring
tail -f /var/www/html/minerva/logs/*.log

# Check for errors
grep ERROR /var/www/html/minerva/logs/*.log

# View scheduler activity
cat /var/www/html/minerva/logs/scheduler.log
```

### Database Health Check

```sql
-- Count venues by source
SELECT source, COUNT(*) as count 
FROM venues 
WHERE is_active = 1 
GROUP BY source 
ORDER BY count DESC;

-- Check data freshness
SELECT 
    source, 
    COUNT(*) as venues,
    AVG(confidence_score) as avg_confidence,
    MAX(last_updated) as last_update
FROM venues
WHERE is_active = 1
GROUP BY source;

-- Find duplicate clusters pending review
SELECT COUNT(*) as pending_reviews
FROM duplicate_clusters
WHERE resolution = 'pending';
```

### Manual Trigger

Run any job manually:

```bash
# Run specific source via scheduler
php /var/www/html/minerva/api/sync_scheduler.php usda_farmers_market

# Run government ingestion directly
php /var/www/html/minerva/api/ingest_government_data.php

# Run deduplication
php /var/www/html/minerva/api/merge_enrich.php
```

## Performance Tuning

### MySQL Optimization

Add these indexes if slow:

```sql
-- For frequent bounding box queries
ALTER TABLE venues ADD SPATIAL INDEX idx_geo_point (geo_point);

-- For source filtering
ALTER TABLE venues ADD INDEX idx_source_active (source, is_active);
```

### Caching

The API caches responses for 5 minutes via headers. For additional caching:

```apache
# In .htaccess or Apache config
<IfModule mod_expires.c>
    ExpiresActive On
    ExpiresByType application/json "access plus 5 minutes"
</IfModule>
```

## Troubleshooting

### "Script not found" errors
Ensure all files are uploaded and permissions are correct:
```bash
chmod 755 /var/www/html/minerva/api/*.php
chmod 755 /var/www/html/minerva/config/
chmod 777 /var/www/html/minerva/logs/
chmod 777 /var/www/html/minerva/data/
```

### Database connection errors
Verify credentials in `config/database.php` match your MySQL setup.

### Rate limiting from APIs
The scripts include built-in rate limiting. If you hit limits:
- Increase sleep times in the ingestion scripts
- Spread cron jobs across different hours
- Use API cache table more aggressively

### Memory issues with large datasets
Increase PHP memory limit:
```bash
php -d memory_limit=512M /var/www/html/minerva/api/ingest_government_data.php
```

## Data Quality

### Confidence Scores
Venues are scored 0-1 based on:
- Government license data: +0.20
- Contact info (phone/website): +0.10 each
- Hours data: +0.10
- Ratings: +0.10
- Crowdsourced sources: -0.10 (lower baseline)

### Deduplication
Automatic merging happens when:
- Venues within 50 meters
- Name similarity > 80%
- OR same license number

Manual review flagged for:
- Name similarity 60-80%

Review pending merges:
```sql
SELECT * FROM duplicate_clusters WHERE resolution = 'pending';
```

## Roadmap

### Phase 2 (Next)
- [ ] Add more county data sources
- [ ] Real-time hours verification
- [ ] Photo aggregation from multiple sources
- [ ] User-submitted corrections workflow

### Phase 3 (Future)
- [ ] Machine learning for duplicate detection
- [ ] Automated data freshness validation
- [ ] Menu data integration
- [ ] Mobile app sync

## Support

For issues or questions:
1. Check logs first: `/var/www/html/minerva/logs/`
2. Verify database connection
3. Check API rate limits
4. Review the sync_log table for error details

---

**Built with data from:**
- Florida DBPR
- Miami-Dade County
- Orange County
- USDA
- OpenStreetMap contributors
- Overture Maps

**Neutral Eats v2.0** - No ads. No bias. Just food.
