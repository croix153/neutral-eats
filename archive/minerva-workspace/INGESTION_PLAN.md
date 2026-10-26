# Neutral Eats - Data Expansion Plan
**Date:** March 12, 2026  
**Status:** ✅ Pipeline Deployed & Running

---

## 🎯 The Problem
- Orlando area: **213 venues** (sparse coverage)
- Miami area: **~2,000+ venues** (good coverage)
- Uneven data distribution across Florida

## ✅ The Solution
**Background Ingestion Pipeline** - API calls happen once centrally, users get instant local queries

### Architecture
```
┌─────────────────────────────────────────────────────────────┐
│                    USER REQUEST (Fast!)                     │
│                      ↓ 50-100ms                             │
│                 Local MySQL DB                              │
└─────────────────────────────────────────────────────────────┘
                              ↑
                    Background Ingestion
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
   ┌────▼────┐          ┌────▼────┐          ┌────▼────┐
   │Overture │          │  OSM    │          │  Yelp   │
   │(FREE)   │          │(FREE)   │          │(5K/day) │
   └─────────┘          └─────────┘          └─────────┘
```

---

## 🚀 What's Running Now

### Phase 1: Central Florida Priority (ACTIVE)
**12 grid cells covering:**
- Downtown Orlando / Dr Phillips
- Winter Park / East Orlando
- UCF Area
- International Drive / Airport
- Disney / Kissimmee
- Windermere / Ocoee
- Altamonte / Lake Mary
- Oviedo

**Expected:** 500-1,000 new venues in Orlando area

### Phase 2: Tampa Bay (Next)
- Downtown Tampa, Clearwater, St Pete
- Suburbs: Brandon, Riverview, Wesley Chapel

### Phase 3: Statewide (Later)
- Jacksonville, Gainesville, Tallahassee
- Naples, Fort Myers, Sarasota
- All suburbs and rural areas

---

## 📊 Data Sources (All Free Tier)

| Source | Daily Limit | Coverage | Quality |
|--------|-------------|----------|---------|
| **Overture Maps** | Unlimited | Good | High |
| **OSM Overpass** | ~1,000 calls | Excellent | Medium |
| **Yelp Fusion** | 5,000 calls | Excellent | Very High |
| **Foursquare** | Free tier | Good | High |

**Rate Limiting:** Respects all API limits to avoid bans

---

## ⏰ Schedule

### Automated (Cron)
- **1:00 AM - 6:00 AM:** Every 30 minutes (off-peak)
- **12:00 PM (noon):** Once daily (daytime update)

### Manual Trigger
```bash
ssh minerva@74.207.224.129
cd /var/www/html/minerva
python3 ingestion_pipeline.py --central-fl
```

---

## 📈 Expected Timeline

| Phase | Duration | New Venues (Est.) |
|-------|----------|-------------------|
| Central FL (active) | 1-2 days | +500-1,000 |
| Tampa Bay | 2-3 days | +800-1,500 |
| Statewide | 1-2 weeks | +3,000-5,000 |
| **Total** | **2-3 weeks** | **+5,000-8,000** |

**Final Target:** 8,000-10,000 venues across Florida

---

## 🔧 Technical Details

### File Locations
- **Pipeline:** `/var/www/html/minerva/ingestion_pipeline.py`
- **Scheduler:** `/var/www/html/minerva/ingestion_scheduler.py`
- **Logs:** `/var/www/html/minerva/data/ingestion.log`
- **State:** `/var/www/html/minerva/data/ingestion_state.json`

### Database Schema
- Deduplication: Within 50 meters + same name
- Updates: Incremental (won't re-add existing)
- Sources tracked: `overture`, `osm`, `yelp`, `foursquare`

### Frontend Behavior
- ✅ **NO external API calls per user**
- ✅ Queries local MySQL only
- ✅ Sub-100ms response times
- ✅ Falls back to sample data if API fails

---

## 🔑 Optional: Add Yelp API Key (Better Coverage)

Yelp has the best restaurant data. Free tier: 5,000 calls/day.

**To add:**
1. Get key: https://www.yelp.com/developers
2. SSH to server
3. Edit: `/var/www/html/minerva/ingestion_pipeline.py`
4. Set: `YELP_API_KEY = 'REDACTED'`

---

## 📊 Monitoring

**Check progress:**
```bash
# View logs
ssh minerva@74.207.224.129 "tail -f /var/www/html/minerva/data/ingestion.log"

# Check venue count
ssh minerva@74.207.224.129 "mysql -u neutraleats_user -pneutraleats_pass neutraleats -e 'SELECT COUNT(*) FROM venues;'"

# Check by source
ssh minerva@74.207.224.129 "mysql -u neutraleats_user -pneutraleats_pass neutraleats -e 'SELECT source, COUNT(*) FROM venues GROUP BY source;'"
```

---

## ✅ Status Right Now

- ✅ Pipeline deployed
- ✅ Initial Central Florida ingestion **running**
- ✅ Cron scheduled for ongoing updates
- ✅ Frontend using local DB only
- ⏳ Waiting for data to populate...

**Check neutraleats.com tomorrow morning** - Orlando should have noticeably more venues! 🦉✨
