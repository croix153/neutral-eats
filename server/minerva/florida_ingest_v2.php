<?php
/**
 * Florida Restaurant Ingestion - Enhanced Version with City Extraction
 * Uses Overture Maps + Overpass API (no API key required)
 * Properly extracts city from address data
 */

// Database configuration
$dbHost = 'localhost';
$dbName = 'neutraleats';
$dbUser = 'neutraleats_user';
$dbPass = 'neutraleats_pass';

$logFile = __DIR__ . '/../data/florida_ingest.log';

// 61 Florida metro/urban areas - Lake Mary first as requested
$floridaAreas = [
    // Starting with Lake Mary as requested
    ['name' => 'Lake Mary', 'lat' => 28.760, 'lng' => -81.350],
    
    // Orlando Metro
    ['name' => 'Downtown Orlando', 'lat' => 28.540, 'lng' => -81.380],
    ['name' => 'Winter Park', 'lat' => 28.600, 'lng' => -81.340],
    ['name' => 'Kissimmee', 'lat' => 28.300, 'lng' => -81.420],
    ['name' => 'Sanford', 'lat' => 28.800, 'lng' => -81.270],
    ['name' => 'Dr Phillips', 'lat' => 28.430, 'lng' => -81.490],
    ['name' => 'UCF Area', 'lat' => 28.600, 'lng' => -81.200],
    ['name' => 'Altamonte Springs', 'lat' => 28.660, 'lng' => -81.390],
    ['name' => 'Oviedo', 'lat' => 28.670, 'lng' => -81.210],
    
    // Tampa Bay
    ['name' => 'Downtown Tampa', 'lat' => 27.950, 'lng' => -82.460],
    ['name' => 'St Petersburg', 'lat' => 27.770, 'lng' => -82.640],
    ['name' => 'Clearwater', 'lat' => 27.970, 'lng' => -82.800],
    ['name' => 'Ybor City', 'lat' => 27.960, 'lng' => -82.430],
    ['name' => 'Hyde Park', 'lat' => 27.930, 'lng' => -82.480],
    ['name' => 'Brandon', 'lat' => 27.940, 'lng' => -82.290],
    
    // Miami / Fort Lauderdale
    ['name' => 'Downtown Miami', 'lat' => 25.770, 'lng' => -80.190],
    ['name' => 'South Beach', 'lat' => 25.790, 'lng' => -80.130],
    ['name' => 'Wynwood', 'lat' => 25.800, 'lng' => -80.200],
    ['name' => 'Coral Gables', 'lat' => 25.750, 'lng' => -80.260],
    ['name' => 'Fort Lauderdale', 'lat' => 26.120, 'lng' => -80.140],
    ['name' => 'Hollywood FL', 'lat' => 26.010, 'lng' => -80.170],
    ['name' => 'Boca Raton', 'lat' => 26.370, 'lng' => -80.080],
    ['name' => 'Pompano Beach', 'lat' => 26.240, 'lng' => -80.130],
    
    // Jacksonville
    ['name' => 'Downtown Jacksonville', 'lat' => 30.330, 'lng' => -81.660],
    ['name' => 'Riverside', 'lat' => 30.310, 'lng' => -81.690],
    ['name' => 'San Marco', 'lat' => 30.300, 'lng' => -81.660],
    ['name' => 'Beaches', 'lat' => 30.290, 'lng' => -81.390],
    ['name' => 'Orange Park', 'lat' => 30.170, 'lng' => -81.710],
    
    // Other Major Cities
    ['name' => 'Gainesville', 'lat' => 29.650, 'lng' => -82.320],
    ['name' => 'Tallahassee', 'lat' => 30.440, 'lng' => -84.280],
    ['name' => 'Naples', 'lat' => 26.140, 'lng' => -81.790],
    ['name' => 'Fort Myers', 'lat' => 26.640, 'lng' => -81.870],
    ['name' => 'Sarasota', 'lat' => 27.340, 'lng' => -82.540],
    ['name' => 'Bradenton', 'lat' => 27.500, 'lng' => -82.570],
    ['name' => 'Daytona Beach', 'lat' => 29.210, 'lng' => -81.020],
    ['name' => 'West Palm Beach', 'lat' => 26.720, 'lng' => -80.050],
    ['name' => 'Pensacola', 'lat' => 30.420, 'lng' => -87.220],
    ['name' => 'Panama City', 'lat' => 30.160, 'lng' => -85.660],
    ['name' => 'Lakeland', 'lat' => 28.040, 'lng' => -81.950],
    ['name' => 'Ocala', 'lat' => 29.190, 'lng' => -82.130],
    ['name' => 'Melbourne', 'lat' => 28.080, 'lng' => -80.610],
    ['name' => 'Palm Bay', 'lat' => 27.920, 'lng' => -80.670],
    ['name' => 'Port St Lucie', 'lat' => 27.270, 'lng' => -80.350],
    ['name' => 'Vero Beach', 'lat' => 27.640, 'lng' => -80.400],
    ['name' => 'The Villages', 'lat' => 28.930, 'lng' => -81.980],
    
    // Additional metros to reach 61
    ['name' => 'Cape Coral', 'lat' => 26.560, 'lng' => -81.950],
    ['name' => 'Bonita Springs', 'lat' => 26.340, 'lng' => -81.780],
    ['name' => 'Winter Haven', 'lat' => 28.020, 'lng' => -81.730],
    ['name' => 'Deltona', 'lat' => 28.900, 'lng' => -81.260],
    ['name' => 'Palm Coast', 'lat' => 29.580, 'lng' => -81.210],
    ['name' => 'Doral', 'lat' => 25.820, 'lng' => -80.350],
    ['name' => 'Hialeah', 'lat' => 25.860, 'lng' => -80.300],
    ['name' => 'Pembroke Pines', 'lat' => 26.010, 'lng' => -80.310],
    ['name' => 'Davie', 'lat' => 26.080, 'lng' => -80.240],
    
    // Rural/smaller areas
    ['name' => 'Lake Wales', 'lat' => 27.900, 'lng' => -81.580],
    ['name' => 'Sebring', 'lat' => 27.490, 'lng' => -81.440],
    ['name' => 'Okeechobee', 'lat' => 27.240, 'lng' => -80.830],
    ['name' => 'Clewiston', 'lat' => 26.750, 'lng' => -81.310],
    ['name' => 'Arcadia', 'lat' => 27.210, 'lng' => -81.850],
    ['name' => 'Wauchula', 'lat' => 27.540, 'lng' => -81.810],
    ['name' => 'Live Oak', 'lat' => 30.290, 'lng' => -82.980],
    ['name' => 'Lake City', 'lat' => 30.190, 'lng' => -82.640],
    ['name' => 'Palatka', 'lat' => 29.640, 'lng' => -81.650],
    ['name' => 'St Augustine', 'lat' => 29.890, 'lng' => -81.310],
    ['name' => 'Key West', 'lat' => 24.550, 'lng' => -81.800],
];

$gridSize = 0.04; // ~4km cells

// City mapping from lat/lng for Florida areas (fallback when address data is missing)
// Format: [lat_min, lat_max, lng_min, lng_max, city_name]
$cityMapping = [
    [28.4, 28.8, -81.6, -81.1, 'Orlando'],
    [27.7, 28.1, -82.9, -82.2, 'Tampa'],
    [25.6, 26.5, -80.4, -79.9, 'Miami'],
    [30.0, 30.6, -82.0, -81.2, 'Jacksonville'],
    [29.4, 29.9, -82.6, -82.0, 'Gainesville'],
    [30.2, 30.7, -84.5, -84.0, 'Tallahassee'],
    [26.0, 26.5, -82.0, -81.5, 'Naples'],
    [26.4, 27.0, -82.2, -81.6, 'Fort Myers'],
    [27.2, 27.6, -82.8, -82.3, 'Sarasota'],
    [29.0, 29.5, -81.3, -80.7, 'Daytona Beach'],
    [26.5, 27.0, -80.3, -79.9, 'West Palm Beach'],
    [30.2, 30.7, -87.5, -86.9, 'Pensacola'],
    [29.9, 30.5, -86.0, -85.3, 'Panama City'],
    [27.8, 28.3, -82.2, -81.7, 'Lakeland'],
    [28.9, 29.5, -82.4, -81.8, 'Ocala'],
    [27.7, 28.4, -81.0, -80.4, 'Melbourne'],
    [27.0, 27.5, -80.6, -80.1, 'Port Saint Lucie'],
    [27.4, 28.0, -80.7, -80.1, 'Vero Beach'],
    [28.7, 29.2, -82.2, -81.7, 'The Villages'],
    [26.4, 26.9, -82.1, -81.7, 'Cape Coral'],
    [24.3, 25.0, -82.0, -81.5, 'Key West'],
];

function logMessage($msg) {
    global $logFile;
    $line = date('Y-m-d H:i:s') . ' ' . $msg . PHP_EOL;
    echo $line;
    file_put_contents($logFile, $line, FILE_APPEND | LOCK_EX);
}

function initDatabase() {
    global $dbHost, $dbName, $dbUser, $dbPass;
    
    $dsn = "mysql:host=$dbHost;dbname=$dbName;charset=utf8mb4";
    $pdo = new PDO($dsn, $dbUser, $dbPass);
    $pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
    return $pdo;
}

function getGridKey($lat, $lng, $gridSize) {
    $gridLat = floor($lat / $gridSize) * $gridSize;
    $gridLng = floor($lng / $gridSize) * $gridSize;
    return sprintf('%.4f,%.4f', $gridLat, $gridLng);
}

function inferCityFromCoords($lat, $lng) {
    global $cityMapping;
    
    foreach ($cityMapping as $bounds) {
        if ($lat >= $bounds[0] && $lat <= $bounds[1] && 
            $lng >= $bounds[2] && $lng <= $bounds[3]) {
            return $bounds[4];
        }
    }
    return 'Florida';
}

function fetchOvertureData($south, $west, $north, $east) {
    $bbox = sprintf('%.4f,%.4f,%.4f,%.4f', $west, $south, $east, $north);
    $url = "https://www.fused.io/server/v1/realtime-shared/UDF_Overture_Maps_Example/run/file?bbox={$bbox}&overture_type=place&format=geojson";
    
    $ch = curl_init($url);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_TIMEOUT, 30);
    curl_setopt($ch, CURLOPT_FOLLOWLOCATION, true);
    curl_setopt($ch, CURLOPT_USERAGENT, 'NeutralEatsBot/1.0');
    
    $response = curl_exec($ch);
    $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);
    
    if ($httpCode !== 200 || !$response) {
        return [];
    }
    
    $data = json_decode($response, true);
    return $data['features'] ?? [];
}

function fetchOverpassData($south, $west, $north, $east) {
    $bbox = sprintf('%.4f,%.4f,%.4f,%.4f', $south, $west, $north, $east);
    
    $query = "[out:json][timeout:60];
(
  node['amenity'='restaurant']($bbox);
  way['amenity'='restaurant']($bbox);
  node['amenity'='cafe']($bbox);
  way['amenity'='cafe']($bbox);
  node['amenity'='bar']($bbox);
  way['amenity'='bar']($bbox);
  node['amenity'='pub']($bbox);
  way['amenity'='pub']($bbox);
  node['amenity'='fast_food']($bbox);
  way['amenity'='fast_food']($bbox);
  node['amenity'='ice_cream']($bbox);
  way['amenity'='ice_cream']($bbox);
  node['amenity'='biergarten']($bbox);
  way['amenity'='biergarten']($bbox);
  node['amenity'='food_court']($bbox);
  way['amenity'='food_court']($bbox);
  node['shop'='bakery']($bbox);
  way['shop'='bakery']($bbox);
  node['shop'='confectionery']($bbox);
  way['shop'='confectionery']($bbox);
  node['shop'='wine']($bbox);
  way['shop'='wine']($bbox);
  node['shop'='deli']($bbox);
  way['shop'='deli']($bbox);
  node['shop'='coffee']($bbox);
  way['shop'='coffee']($bbox);
);out body center;";
    
    $url = 'https://overpass-api.de/api/interpreter?data=' . urlencode($query);
    
    $ch = curl_init($url);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_TIMEOUT, 60);
    curl_setopt($ch, CURLOPT_FOLLOWLOCATION, true);
    curl_setopt($ch, CURLOPT_USERAGENT, 'NeutralEatsBot/1.0');
    
    $response = curl_exec($ch);
    $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);
    
    if ($httpCode !== 200 || !$response) {
        return [];
    }
    
    $data = json_decode($response, true);
    return $data['elements'] ?? [];
}

function parseOvertureVenues($features, $defaultCity) {
    $venues = [];
    foreach ($features as $f) {
        $p = $f['properties'] ?? [];
        $c = $f['geometry']['coordinates'] ?? [0, 0];
        
        $cats = $p['categories'] ?? [];
        $catStr = strtolower(implode(' ', $cats));
        
        if (!preg_match('/restaurant|cafe|coffee|bar|pub|food|dining|bakery/', $catStr)) {
            continue;
        }
        
        $type = 'restaurant';
        if (strpos($catStr, 'cafe') !== false || strpos($catStr, 'coffee') !== false || strpos($catStr, 'bakery') !== false) {
            $type = 'cafe';
        } elseif (strpos($catStr, 'bar') !== false || strpos($catStr, 'pub') !== false || strpos($catStr, 'nightclub') !== false) {
            $type = 'bar';
        }
        
        // Extract city from address data if available
        $city = $defaultCity;
        if (isset($p['addresses']) && is_array($p['addresses'])) {
            foreach ($p['addresses'] as $addr) {
                if (isset($addr['locality'])) {
                    $city = $addr['locality'];
                    break;
                }
            }
        }
        
        // Try to infer from coordinates if still default
        if ($city === $defaultCity && isset($c[1], $c[0])) {
            $inferred = inferCityFromCoords($c[1], $c[0]);
            if ($inferred !== 'Florida') {
                $city = $inferred;
            }
        }
        
        $venues[] = [
            'id' => 'ovt:' . ($p['id'] ?? uniqid()),
            'name' => $p['names']['primary'] ?? $p['name'] ?? 'Unnamed',
            'lat' => floatval($c[1]),
            'lng' => floatval($c[0]),
            'type' => $type,
            'cuisine' => $cats[0] ?? 'Various',
            'city' => $city,
            'brand' => $p['brands'][0] ?? '',
            'source' => 'overture',
            'source_id' => $p['id'] ?? null
        ];
    }
    return $venues;
}

function parseOverpassVenues($elements, $defaultCity) {
    $venues = [];
    foreach ($elements as $e) {
        if ($e['type'] === 'node') {
            if (!isset($e['lat'], $e['lon'])) continue;
            $lat = $e['lat'];
            $lng = $e['lon'];
        } elseif ($e['type'] === 'way') {
            if (!isset($e['center']['lat'], $e['center']['lon'])) continue;
            $lat = $e['center']['lat'];
            $lng = $e['center']['lon'];
        } else {
            continue;
        }
        
        $tags = $e['tags'] ?? [];
        $name = $tags['name'] ?? $tags['name:en'] ?? $tags['brand'] ?? '';
        if (!$name) continue;
        
        $type = $tags['amenity'] ?? $tags['shop'] ?? 'unknown';
        if ($type === 'pub' || $type === 'biergarten') $type = 'bar';
        if ($type === 'fast_food' || $type === 'ice_cream' || $type === 'food_court') $type = 'restaurant';
        if (isset($tags['shop'])) {
            if (in_array($tags['shop'], ['bakery', 'pastry', 'confectionery', 'coffee'])) {
                $type = 'cafe';
            } elseif (in_array($tags['shop'], ['wine', 'alcohol'])) {
                $type = 'bar';
            } elseif ($tags['shop'] === 'deli') {
                $type = 'restaurant';
            }
        }
        
        if (!in_array($type, ['restaurant', 'cafe', 'bar'])) continue;
        
        // Extract city from address tags
        $city = $defaultCity;
        if (isset($tags['addr:city'])) {
            $city = $tags['addr:city'];
        } elseif (isset($tags['addr:suburb'])) {
            $city = $tags['addr:suburb'];
        } else {
            // Infer from coordinates
            $inferred = inferCityFromCoords($lat, $lng);
            if ($inferred !== 'Florida') {
                $city = $inferred;
            }
        }
        
        $venues[] = [
            'id' => 'osm:' . $e['type'] . ':' . $e['id'],
            'name' => $name,
            'lat' => floatval($lat),
            'lng' => floatval($lng),
            'type' => $type,
            'cuisine' => $tags['cuisine'] ?? $tags['diet'] ?? 'Various',
            'city' => $city,
            'brand' => $tags['brand'] ?? '',
            'source' => 'osm',
            'source_id' => $e['id']
        ];
    }
    return $venues;
}

// Canonical venues.grid_cell (matches pipeline/merge_overture.py): the
// venue's OWN 0.02-degree cell — never the fetch area's cell.
function canonicalGridCell($lat, $lng) {
    return sprintf('%.3f,%.3f', floor($lat / 0.02) * 0.02, floor($lng / 0.02) * 0.02);
}

function ingestArea($pdo, $name, $lat, $lng, $gridSize) {
    logMessage("Processing: $name ($lat, $lng)");
    
    $cellKey = getGridKey($lat, $lng, $gridSize);
    
    $gridLat = floor($lat / $gridSize) * $gridSize;
    $gridLng = floor($lng / $gridSize) * $gridSize;
    $south = $gridLat;
    $north = $gridLat + $gridSize;
    $west = $gridLng;
    $east = $gridLng + $gridSize;
    
    // Check if recently updated
    $stmt = $pdo->prepare('SELECT last_fetched FROM grid_cells WHERE cell_key = :cell');
    $stmt->execute([':cell' => $cellKey]);
    $row = $stmt->fetch(PDO::FETCH_ASSOC);
    if ($row && (time() - intval($row['last_fetched'])) < 604800) {
        logMessage("  Skipping - updated within last 7 days");
        return 0;
    }
    
    $allVenues = [];
    
    logMessage("  Fetching Overture...");
    $overtureFeatures = fetchOvertureData($south, $west, $north, $east);
    $overtureVenues = parseOvertureVenues($overtureFeatures, $name);
    logMessage("  Overture: " . count($overtureVenues) . " venues");
    $allVenues = array_merge($allVenues, $overtureVenues);
    
    logMessage("  Fetching Overpass...");
    $overpassElements = fetchOverpassData($south, $west, $north, $east);
    $overpassVenues = parseOverpassVenues($overpassElements, $name);
    logMessage("  Overpass: " . count($overpassVenues) . " venues");
    $allVenues = array_merge($allVenues, $overpassVenues);
    
    // Deduplicate
    $seen = [];
    $uniqueVenues = [];
    foreach ($allVenues as $v) {
        $key = sprintf('%s:%.4f:%.4f', $v['name'], $v['lat'], $v['lng']);
        if (!isset($seen[$key])) {
            $seen[$key] = true;
            $uniqueVenues[] = $v;
        }
    }
    
    logMessage("  Total unique: " . count($uniqueVenues) . " venues");
    
    if (count($uniqueVenues) === 0) {
        return 0;
    }
    
    $now = time();
    $inserted = 0;
    
    $stmt = $pdo->prepare('INSERT INTO venues 
        (id, name, lat, lng, type, cuisine, city, brand, source, source_id, last_updated, first_seen, grid_cell)
        VALUES (:id, :name, :lat, :lng, :type, :cuisine, :city, :brand, :source, :source_id, :updated, :first, :cell)
        ON DUPLICATE KEY UPDATE
        name = VALUES(name), lat = VALUES(lat), lng = VALUES(lng), type = VALUES(type),
        cuisine = VALUES(cuisine), city = VALUES(city), brand = VALUES(brand), 
        last_updated = VALUES(last_updated), check_count = check_count + 1');
    
    foreach ($uniqueVenues as $v) {
        try {
            $stmt->execute([
                ':id' => $v['id'],
                ':name' => $v['name'],
                ':lat' => $v['lat'],
                ':lng' => $v['lng'],
                ':type' => $v['type'],
                ':cuisine' => $v['cuisine'],
                ':city' => $v['city'],
                ':brand' => $v['brand'],
                ':source' => $v['source'],
                ':source_id' => $v['source_id'],
                ':updated' => $now,
                ':first' => $now,
                ':cell' => canonicalGridCell($v['lat'], $v['lng'])
            ]);
            $inserted++;
        } catch (PDOException $e) {
            logMessage("  DB Error: " . $e->getMessage());
        }
    }
    
    // Update grid cell
    $stmt = $pdo->prepare('INSERT INTO grid_cells 
        (cell_key, lat_min, lat_max, lng_min, lng_max, venue_count, last_fetched, next_fetch, fetch_count)
        VALUES (:cell, :latMin, :latMax, :lngMin, :lngMax, :count, :now, :next, 1)
        ON DUPLICATE KEY UPDATE
        venue_count = VALUES(venue_count), last_fetched = VALUES(last_fetched), 
        next_fetch = VALUES(next_fetch), fetch_count = fetch_count + 1');
    
    $stmt->execute([
        ':cell' => $cellKey,
        ':latMin' => $south,
        ':latMax' => $north,
        ':lngMin' => $west,
        ':lngMax' => $east,
        ':count' => count($uniqueVenues),
        ':now' => $now,
        ':next' => $now + 604800
    ]);
    
    logMessage("  Inserted/updated: $inserted venues");
    return $inserted;
}

// Main execution
logMessage("=== FLORIDA STATE INGESTION STARTED ===");
logMessage("Target: " . count($floridaAreas) . " areas");
logMessage("Starting with Lake Mary as requested");

$pdo = initDatabase();

$totalVenues = 0;
$processed = 0;
$startTime = time();
$lastReportTime = $startTime;
$lastReportCount = 0;

foreach ($floridaAreas as $area) {
    $count = ingestArea($pdo, $area['name'], $area['lat'], $area['lng'], $gridSize);
    $totalVenues += $count;
    $processed++;
    
    logMessage("Progress: $processed / " . count($floridaAreas) . " areas");
    logMessage("Total venues so far: $totalVenues");
    
    // Report every 50k venues
    if ($totalVenues >= $lastReportCount + 50000) {
        $elapsed = time() - $startTime;
        $venuesPerHour = $elapsed > 0 ? round($totalVenues / ($elapsed / 3600)) : 0;
        logMessage("*** MILESTONE: $totalVenues venues ingested ***");
        logMessage("    Rate: $venuesPerHour venues/hour");
        $lastReportCount = $totalVenues;
    }
    
    // 5-minute progress reports
    if (time() - $lastReportTime >= 300) {
        $elapsed = time() - $startTime;
        $venuesPerHour = $elapsed > 0 ? round($totalVenues / ($elapsed / 3600)) : 0;
        logMessage("*** 5-MIN REPORT: $processed areas, $totalVenues venues, $venuesPerHour/hour ***");
        $lastReportTime = time();
    }
    
    if ($processed < count($floridaAreas)) {
        logMessage("  Sleeping 2 seconds...");
        sleep(2);
    }
}

$totalTime = time() - $startTime;
$avgRate = $totalTime > 0 ? round($totalVenues / ($totalTime / 3600)) : 0;

logMessage("=== FLORIDA INGESTION COMPLETE ===");
logMessage("Total areas processed: $processed");
logMessage("Total venues ingested: $totalVenues");
logMessage("Total time: " . round($totalTime / 60, 2) . " minutes");
logMessage("Average rate: $avgRate venues/hour");

// Final database count
$stmt = $pdo->query("SELECT COUNT(*), COUNT(DISTINCT city) FROM venues");
$row = $stmt->fetch(PDO::FETCH_NUM);
logMessage("Final DB count: {$row[0]} total venues across {$row[1]} distinct cities");
?>
