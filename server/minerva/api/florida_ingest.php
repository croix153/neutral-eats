<?php
/**
 * Florida State Data Ingestion (MySQL Version)
 * Populates database with venues from major Florida metros
 */

// Database configuration
$dbHost = 'localhost';
$dbName = 'neutraleats';
$dbUser = 'neutraleats_user';
$dbPass = 'neutraleats_pass';

$logFile = __DIR__ . '/../data/florida_ingest.log';

// Major Florida metro areas (grid cell centers)
$floridaMetros = [
    // Orlando Metro
    ['name' => 'Downtown Orlando', 'lat' => 28.540, 'lng' => -81.380],
    ['name' => 'Winter Park', 'lat' => 28.600, 'lng' => -81.340],
    ['name' => 'Kissimmee', 'lat' => 28.300, 'lng' => -81.420],
    ['name' => 'Sanford', 'lat' => 28.800, 'lng' => -81.270],
    ['name' => 'Dr Phillips', 'lat' => 28.430, 'lng' => -81.490],
    ['name' => 'UCF Area', 'lat' => 28.600, 'lng' => -81.200],
    
    // Tampa Bay
    ['name' => 'Downtown Tampa', 'lat' => 27.950, 'lng' => -82.460],
    ['name' => 'St Petersburg', 'lat' => 27.770, 'lng' => -82.640],
    ['name' => 'Clearwater', 'lat' => 27.970, 'lng' => -82.800],
    ['name' => 'Ybor City', 'lat' => 27.960, 'lng' => -82.430],
    ['name' => 'Hyde Park', 'lat' => 27.930, 'lng' => -82.480],
    
    // Miami / Fort Lauderdale
    ['name' => 'Downtown Miami', 'lat' => 25.770, 'lng' => -80.190],
    ['name' => 'South Beach', 'lat' => 25.790, 'lng' => -80.130],
    ['name' => 'Wynwood', 'lat' => 25.800, 'lng' => -80.200],
    ['name' => 'Coral Gables', 'lat' => 25.750, 'lng' => -80.260],
    ['name' => 'Fort Lauderdale', 'lat' => 26.120, 'lng' => -80.140],
    ['name' => 'Hollywood FL', 'lat' => 26.010, 'lng' => -80.170],
    ['name' => 'Boca Raton', 'lat' => 26.370, 'lng' => -80.080],
    
    // Jacksonville
    ['name' => 'Downtown Jacksonville', 'lat' => 30.330, 'lng' => -81.660],
    ['name' => 'Riverside', 'lat' => 30.310, 'lng' => -81.690],
    ['name' => 'San Marco', 'lat' => 30.300, 'lng' => -81.660],
    ['name' => 'Beaches', 'lat' => 30.290, 'lng' => -81.390],
    
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
    
    // Rural areas (as requested)
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
    ['name' => 'Fernandina Beach', 'lat' => 30.670, 'lng' => -81.460],
    ['name' => 'Perry', 'lat' => 30.120, 'lng' => -83.580],
    ['name' => 'Apalachicola', 'lat' => 29.720, 'lng' => -84.990],
    ['name' => 'Marianna', 'lat' => 30.770, 'lng' => -85.220],
    ['name' => 'Chipley', 'lat' => 30.780, 'lng' => -85.540],
    ['name' => 'Defuniak Springs', 'lat' => 30.720, 'lng' => -86.110],
    ['name' => 'Milton', 'lat' => 30.630, 'lng' => -87.040],
    ['name' => 'Destin', 'lat' => 30.390, 'lng' => -86.480],
    ['name' => 'Fort Walton Beach', 'lat' => 30.410, 'lng' => -86.620],
    ['name' => 'Key West', 'lat' => 24.550, 'lng' => -81.800],
    ['name' => 'Key Largo', 'lat' => 25.080, 'lng' => -80.440],
    ['name' => 'Marathon', 'lat' => 24.710, 'lng' => -81.090],
];

$gridSize = 0.04; // ~4km cells

function logMessage($msg) {
    global $logFile;
    $line = date('Y-m-d H:i:s') . ' ' . $msg . PHP_EOL;
    echo $line;
    file_put_contents($logFile, $line, FILE_APPEND | LOCK_EX);
}

function getGridKey($lat, $lng, $gridSize) {
    $gridLat = floor($lat / $gridSize) * $gridSize;
    $gridLng = floor($lng / $gridSize) * $gridSize;
    return sprintf('%.3f,%.3f', $gridLat, $gridLng);
}

function initDatabase() {
    global $dbHost, $dbName, $dbUser, $dbPass;
    $pdo = new PDO("mysql:host=$dbHost;charset=utf8mb4", $dbUser, $dbPass);
    $pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
    
    // Create database if not exists
    $pdo->exec("CREATE DATABASE IF NOT EXISTS $dbName CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci");
    $pdo->exec("USE $dbName");
    
    // Create tables
    $schema = file_get_contents(__DIR__ . '/../../neutraleats_mysql_schema.sql');
    // Remove USE statement since we're already using the DB
    $schema = preg_replace('/USE \w+;/', '', $schema);
    $pdo->exec($schema);
    
    return $pdo;
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

function parseOvertureVenues($features) {
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
        
        $venues[] = [
            'id' => 'ovt:' . ($p['id'] ?? uniqid()),
            'name' => $p['names']['primary'] ?? $p['name'] ?? 'Unnamed',
            'lat' => floatval($c[1]),
            'lng' => floatval($c[0]),
            'type' => $type,
            'cuisine' => $cats[0] ?? 'Various',
            'brand' => $p['brands'][0] ?? '',
            'source' => 'overture',
            'source_id' => $p['id'] ?? null
        ];
    }
    return $venues;
}

function parseOverpassVenues($elements) {
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
        
        $venues[] = [
            'id' => 'osm:' . $e['type'] . ':' . $e['id'],
            'name' => $name,
            'lat' => floatval($lat),
            'lng' => floatval($lng),
            'type' => $type,
            'cuisine' => $tags['cuisine'] ?? $tags['diet'] ?? 'Various',
            'brand' => $tags['brand'] ?? '',
            'source' => 'osm',
            'source_id' => $e['id']
        ];
    }
    return $venues;
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
    $overtureVenues = parseOvertureVenues($overtureFeatures);
    logMessage("  Overture: " . count($overtureVenues) . " venues");
    $allVenues = array_merge($allVenues, $overtureVenues);
    
    logMessage("  Fetching Overpass...");
    $overpassElements = fetchOverpassData($south, $west, $north, $east);
    $overpassVenues = parseOverpassVenues($overpassElements);
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
        (id, name, lat, lng, type, cuisine, brand, source, source_id, last_updated, first_seen, grid_cell)
        VALUES (:id, :name, :lat, :lng, :type, :cuisine, :brand, :source, :source_id, :updated, :first, :cell)
        ON DUPLICATE KEY UPDATE
        name = VALUES(name), lat = VALUES(lat), lng = VALUES(lng), type = VALUES(type),
        cuisine = VALUES(cuisine), brand = VALUES(brand), last_updated = VALUES(last_updated), check_count = check_count + 1');
    
    foreach ($uniqueVenues as $v) {
        $stmt->execute([
            ':id' => $v['id'],
            ':name' => $v['name'],
            ':lat' => $v['lat'],
            ':lng' => $v['lng'],
            ':type' => $v['type'],
            ':cuisine' => $v['cuisine'],
            ':brand' => $v['brand'],
            ':source' => $v['source'],
            ':source_id' => $v['source_id'],
            ':updated' => $now,
            ':first' => $now,
            ':cell' => $cellKey
        ]);
        $inserted++;
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
logMessage("Target: " . count($floridaMetros) . " areas (metros + rural)");

$pdo = initDatabase();

$totalVenues = 0;
$processed = 0;

foreach ($floridaMetros as $metro) {
    $count = ingestArea($pdo, $metro['name'], $metro['lat'], $metro['lng'], $gridSize);
    $totalVenues += $count;
    $processed++;
    
    logMessage("Progress: $processed / " . count($floridaMetros) . " areas");
    logMessage("Total venues so far: $totalVenues");
    
    if ($processed < count($floridaMetros)) {
        logMessage("  Sleeping 3 seconds...");
        sleep(3);
    }
}

logMessage("=== FLORIDA INGESTION COMPLETE ===");
logMessage("Total areas processed: $processed");
logMessage("Total venues ingested: $totalVenues");
logMessage("Coverage: 50+ Florida cities including metros and rural areas");
?>