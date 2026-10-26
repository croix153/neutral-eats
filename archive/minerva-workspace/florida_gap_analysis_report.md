# Neutral Eats Florida Database Gap Analysis Report

**Date:** 2026-02-17  
**Database:** /var/www/html/minerva/data/neutraleats.db  
**Current Status:** 2,444 venues across 29 grid cells

---

## Executive Summary

The Florida database ingestion has **significant coverage gaps**. While the ingestion script attempted to process 65 target areas, the actual database only contains venues from 29 grid cells. Nearly **half of the target areas (31 of 65)** have no meaningful coverage.

### Key Findings:
- ✅ **25 areas** have good coverage (20+ venues)
- ⚠️ **9 areas** have low coverage (<20 venues)  
- ❌ **31 areas** have essentially no coverage

---

## Current Coverage Analysis

### Well-Covered Areas (25)
| Area | Venues | Grid Cell |
|------|--------|-----------|
| Downtown Orlando | 464 | 28.520,-81.400* |
| Downtown Miami | 336 | 25.760,-80.160 |
| South Beach | 336 | 25.760,-80.160 |
| Wynwood | 336 | 25.760,-80.160 |
| Coral Gables | 192 | 25.760,-80.200 |
| Downtown Tampa | 169 | 27.920,-82.480 |
| Ybor City | 169 | 27.920,-82.480 |
| Hyde Park | 169 | 27.920,-82.480 |
| St Petersburg | 132 | 27.760,-82.640 |
| Fort Lauderdale | 111 | 26.120,-80.160 |
| Davie | 111 | 26.120,-80.160 |
| Downtown Jacksonville | 108 | 30.280,-81.720 |
| Riverside | 108 | 30.280,-81.720 |
| San Marco | 108 | 30.280,-81.720 |
| Daytona Beach | 100 | 29.200,-81.040 |
| Naples | 90 | 26.120,-81.800 |
| Tallahassee | 62 | 30.440,-84.280 |
| Lake Mary | 60 | 28.800,-81.280 |
| Sanford | 60 | 28.800,-81.280 |
| Kissimmee | 45 | 28.280,-81.440 |
| Fort Myers | 40 | 26.640,-81.880 |
| Hollywood FL | 29 | 26.000,-80.200 |
| Beaches | 29 | 30.280,-81.400 |
| Sarasota | 28 | 27.320,-82.560 |
| Boca Raton | 20 | 26.360,-80.080 |

*Note: Orlando has data quality issues - grid cell contains contaminated UK data

### Low Coverage Areas (9) - Need Attention
| Area | Venues | Issue |
|------|--------|-------|
| Winter Park | 11 | Only 11 venues for major suburb |
| Dr Phillips | 6 | Very low for busy area |
| UCF Area | 9 | Major university area underrepresented |
| Altamonte Springs | 11 | Should have more |
| Oviedo | 9 | Growing suburb, needs more |
| Clearwater | 18 | Beach town should have more |
| Gainesville | 8 | University town, should have 100+ |
| Bradenton | 10 | Should have more coverage |
| West Palm Beach | 1 | Almost no coverage |

### Missing Areas (31) - No Meaningful Data
These areas were in the target list but have essentially no venues:

**Tampa Area:**
- Brandon (27.94, -82.29) - Major suburb

**Miami/Fort Lauderdale:**
- Pompano Beach (26.24, -80.13)
- Doral (25.82, -80.35) - Major business hub
- Hialeah (25.86, -80.30) - Large city
- Pembroke Pines (26.01, -80.31)

**Central Florida:**
- Lakeland (28.04, -81.95) - Major city
- Ocala (29.19, -82.13)
- Winter Haven (28.02, -81.73)
- Deltona (28.90, -81.26)
- The Villages (28.93, -81.98) - Large retirement community

**Space Coast:**
- Melbourne (28.08, -80.61)
- Palm Bay (27.92, -80.67)

**Treasure Coast:**
- Port St Lucie (27.27, -80.35)
- Vero Beach (27.64, -80.40)
- Palm Coast (29.58, -81.21)

**Southwest Florida:**
- Cape Coral (26.56, -81.95) - Major city
- Bonita Springs (26.34, -81.78)

**Jacksonville Area:**
- Orange Park (30.17, -81.71)

**Panhandle:**
- Pensacola (30.42, -87.22) - Major city
- Panama City (30.16, -85.66)

**North Central:**
- Live Oak (30.29, -82.98)
- Lake City (30.19, -82.64)
- Palatka (29.64, -81.65)

**Historic Coast:**
- St Augustine (29.89, -81.31) - Major tourist destination

**Florida Keys:**
- Key West (24.55, -81.80) - Major destination

**Rural Areas:**
- Lake Wales (27.90, -81.58)
- Sebring (27.49, -81.44)
- Okeechobee (27.24, -80.83)
- Clewiston (26.75, -81.31)
- Arcadia (27.21, -81.85)
- Wauchula (27.54, -81.81)

---

## Critical Missing Suburbs

### Orlando Metro Missing (12 high-priority suburbs)
| Suburb | Coordinates | Priority |
|--------|-------------|----------|
| Ocoee | 28.57, -81.54 | HIGH |
| Windermere | 28.50, -81.53 | HIGH |
| Winter Garden | 28.57, -81.59 | HIGH |
| Avalon Park | 28.55, -81.17 | MEDIUM |
| Waterford Lakes | 28.55, -81.20 | MEDIUM |
| Maitland | 28.63, -81.37 | MEDIUM |
| Apopka | 28.68, -81.51 | MEDIUM |
| Clermont | 28.55, -81.75 | MEDIUM |
| Mount Dora | 28.80, -81.64 | MEDIUM |
| Celebration | 28.32, -81.55 | MEDIUM |
| Hunter's Creek | 28.36, -81.43 | LOW |
| Lake Nona/Medical City | 28.37, -81.28 | HIGH |

### Tampa Bay Missing (10 suburbs)
| Suburb | Coordinates | Priority |
|--------|-------------|----------|
| Riverview | 27.87, -82.33 | HIGH |
| Wesley Chapel | 28.18, -82.35 | HIGH |
| Land O' Lakes | 28.22, -82.45 | MEDIUM |
| Lutz | 28.15, -82.46 | MEDIUM |
| Temple Terrace | 28.07, -82.39 | MEDIUM |
| Plant City | 28.02, -82.12 | MEDIUM |
| Sun City Center | 27.72, -82.35 | LOW |
| Ruskin | 27.72, -82.43 | LOW |
| Valrico | 27.94, -82.24 | MEDIUM |
| FishHawk | 27.85, -82.24 | LOW |

### Miami/Fort Lauderdale Missing (14 suburbs)
| Suburb | Coordinates | Priority |
|--------|-------------|----------|
| Miami Beach | 25.79, -80.13 | HIGH |
| Aventura | 25.96, -80.14 | HIGH |
| Sunny Isles Beach | 25.93, -80.13 | MEDIUM |
| Coral Springs | 26.27, -80.27 | HIGH |
| Miramar | 25.98, -80.30 | HIGH |
| Weston | 26.10, -80.40 | HIGH |
| Plantation | 26.13, -80.23 | MEDIUM |
| Deerfield Beach | 26.32, -80.10 | MEDIUM |
| Boynton Beach | 26.53, -80.07 | MEDIUM |
| Delray Beach | 26.46, -80.07 | HIGH |
| Jupiter | 26.93, -80.09 | MEDIUM |
| Palm Beach Gardens | 26.85, -80.14 | MEDIUM |
| Wellington | 26.66, -80.26 | MEDIUM |
| Kendall | 25.69, -80.32 | HIGH |

---

## Data Quality Issues

### 1. Orlando Grid Cell Contamination
The grid cell `28.520,-81.400` (Orlando) contains venues with UK coordinates (lat ~51.5, lng ~-0.1 mixed with Florida coordinates. This needs cleanup.

### 2. Grid Cell Overlap
Multiple cities are being mapped to the same grid cells, causing:
- South Beach, Wynwood, and Downtown Miami all in one cell
- Ybor City, Hyde Park, Downtown Tampa all in one cell
- Jacksonville neighborhoods overlapping

### 3. Venue Deduplication
The ingestion log shows 22,934 venues were processed but only 2,444 are in the database. This suggests aggressive deduplication or data loss.

---

## Recommended Action Plan

### Phase 1: Fix Data Quality (Week 1)
1. **Clean Orlando data** - Remove UK venues from Florida database
2. **Verify deduplication logic** - Ensure venues aren't being incorrectly removed
3. **Add grid cell validation** - Ensure fetched venues match expected geography

### Phase 2: High-Priority Missing Areas (Week 2-3)
Add these 20 high-priority areas:

**Orlando (6):**
- Ocoee (28.57, -81.54)
- Windermere (28.50, -81.53)
- Winter Garden (28.57, -81.59)
- Lake Nona/Medical City (28.37, -81.28)
- Maitland (28.63, -81.37)
- Apopka (28.68, -81.51)

**Tampa (4):**
- Riverview (27.87, -82.33)
- Wesley Chapel (28.18, -82.35)
- Brandon (27.94, -82.29) - re-ingest
- Valrico (27.94, -82.24)

**Miami/FLL (6):**
- Miami Beach (25.79, -80.13)
- Aventura (25.96, -80.14)
- Coral Springs (26.27, -80.27)
- Miramar (25.98, -80.30)
- Weston (26.10, -80.40)
- Delray Beach (26.46, -80.07)
- Kendall (25.69, -80.32)

**Major Cities (4):**
- Lakeland (28.04, -81.95) - re-ingest
- Gainesville (29.65, -82.32) - re-ingest with higher radius
- Pensacola (30.42, -87.22) - re-ingest
- Cape Coral (26.56, -81.95) - re-ingest

### Phase 3: Medium Priority (Week 4)
Add 15 medium-priority suburbs:
- Avalon Park, Waterford Lakes, Clermont, Mount Dora, Celebration (Orlando)
- Land O' Lakes, Lutz, Temple Terrace, Plant City (Tampa)
- Sunny Isles, Plantation, Deerfield, Boynton, Jupiter (Miami/FLL)

### Phase 4: Smaller Cities & Cleanup (Week 5)
- Re-ingest all 31 missing areas from original list
- Add smaller suburbs based on user demand
- Final data quality verification

---

## Expected Results After Implementation

| Metric | Current | After Phase 1 | After Phase 2 | After Phase 3 |
|--------|---------|---------------|---------------|---------------|
| Total Venues | 2,444 | 2,200* | 5,000+ | 8,000+ |
| Grid Cells | 29 | 29 | 50+ | 65+ |
| Major Metros Covered | 3 | 3 | 5 | 5 |
| Suburbs Covered | 12 | 12 | 32 | 50+ |

*After cleanup of contaminated data

---

## Appendices

### A. Complete List of 65 Original Target Areas
[See florida_ingest.php for full list]

### B. Database Query for Monitoring
```sql
-- Check coverage by grid cell
SELECT grid_cell, COUNT(*) as venues 
FROM venues 
GROUP BY grid_cell 
ORDER BY venues DESC;

-- Check for out-of-bounds venues ( contamination)
SELECT * FROM venues 
WHERE lat < 24 OR lat > 31 OR lng < -88 OR lng > -79;
```

### C. Priority Scoring Methodology
- **HIGH**: Major suburbs with 50K+ population or significant commercial activity
- **MEDIUM**: Established suburbs with retail/restaurant presence  
- **LOW**: Smaller communities or bedroom suburbs

---

*Report generated: 2026-02-17*
*Analyst: Neutral Eats Database Audit System*
