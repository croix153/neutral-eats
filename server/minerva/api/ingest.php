<?php
/**
 * Neutral Eats Data Ingestion Script
 * Fetches venue data from Overture Maps and OpenStreetMap
 * 
 * Usage: php ingest.php [grid_cell] [--force]
 *   grid_cell: Optional specific cell to update (e.g., "28.540,-81.380")
 *   --force: Force refresh even if recently updated
 */

$dbPath = __DIR__ . '/../data/neutraleats.db';
$logFile = __DIR__ . '/../data/ingest.log';

// Orlando area grid cells to pre-populate
$orlandoGridCells = [
    '28.540,-81.380', // Downtown
    '28.520,-81.380', // Sodo
    '28.560,-81.380', // Winter Park
    '28.540,-81.360', // East Orlando
    '28.540,-81.400', // West Orlando
    '28.500,-81.380', // Airport area
    '28.580,-81.380', // North
];

function logMessage($msg) {
    global $logFile;
    $line = date('Y-m-d H:i:s') . ' ' . $msg . PHP_EOL;
    echo $line;
    file_put_contents($logFile, $line, FILE_APPEND | LOCK_EX);
}

function initDatabase($dbPath) {
    if (!is_dir(dirname($dbPath))) {
        mkdir(dirname($dbPath), 0755, true);
    }
    
    $db = new SQLite3($dbPath);
    $db->busyTimeout(10000);
    
    // Create tables if not exists
    $schema = file_get_contents(__DIR__ . '/../../neutraleats_schema.sql');
    $db->exec($schema);
    
    return $db;
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
        logMessage("Overture API failed: HTTP $httpCode");
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
        logMessage("Overpass API failed: HTTP $httpCode");
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
            'source_id' => $p['id'] ?? null,
            'rating' => null,
            'price_level' => null,
            'address' => null,
            'city' => null,
            'state' => null,
            'zip' => null,
            'phone' => null,
            'website' => null
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
        if ($tags['shop']) {
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
            'source_id' => $e['id'],
            'rating' => null,
            'price_level' => null,
            'address' => $tags['addr:street'] ?? null,
            'city' => $tags['addr:city'] ?? null,
            'state' => $tags['addr:state'] ?? null,
            'zip' => $tags['addr:postcode'] ?? null,
            'phone' => $tags['phone'] ?? $tags['contact:phone'] ?? null,
            'website' => $tags['website'] ?? $tags['contact:website'] ?? null
        ];
    }
    return $venues;
}

function updateGridCell($db, $cellKey, $venues) {
    $parts = explode(',', $cellKey);
    $lat = floatval($parts[0]);
    $lng = floatval($parts[1]);
    $gridSize = 0.02;
    
    $latMin = $lat;
    $latMax = $lat + $gridSize;
    $lngMin = $lng;
    $lngMax = $lng + $gridSize;
    
    $stmt = $db->prepare('INSERT OR REPLACE INTO grid_cells 
        (cell_key, lat_min, lat_max, lng_min, lng_max, venue_count, last_fetched, next_fetch, fetch_count)
        VALUES (:cell, :latMin, :latMax, :lngMin, :lngMax, :count, :now, :next, 
            COALESCE((SELECT fetch_count FROM grid_cells WHERE cell_key = :cell), 0) + 1)');
    
    $stmt->bindValue(':cell', $cellKey);
    $stmt->bindValue(':latMin', $latMin);
    $stmt->bindValue(':latMax', $latMax);
    $stmt->bindValue(':lngMin', $lngMin);
    $stmt->bindValue(':lngMax', $lngMax);
    $stmt->bindValue(':count', count($venues));
    $stmt->bindValue(':now', time());
    $stmt->bindValue(':next', time() + 604800); // 7 days
    $stmt->execute();
}

function ingestGridCell($db, $cellKey, $force = false) {
    logMessage("Processing grid cell: $cellKey");
    
    // Check if recently updated
    if (!$force) {
        $stmt = $db->prepare('SELECT last_fetched FROM grid_cells WHERE cell_key = :cell');
        $stmt->bindValue(':cell', $cellKey);
        $result = $stmt->execute();
        $row = $result->fetchArray(SQLITE3_ASSOC);
        if ($row && (time() - intval($row['last_fetched'])) < 86400) { // 24 hours
            logMessage("  Skipping - updated within last 24 hours");
            return;
        }
    }
    
    $parts = explode(',', $cellKey);
    $lat = floatval($parts[0]);
    $lng = floatval($parts[1]);
    $gridSize = 0.02;
    
    $south = $lat;
    $north = $lat + $gridSize;
    $west = $lng;
    $east = $lng + $gridSize;
    
    // Fetch from both sources
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
    
    // Deduplicate by name+lat+lng (within 50m)
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
    
    // Insert/update database
    $now = time();
    $inserted = 0;
    $updated = 0;
    
    $stmt = $db->prepare('INSERT INTO venues 
        (id, name, lat, lng, type, cuisine, brand, source, source_id, rating, price_level, 
         address, city, state, zip, phone, website, last_updated, first_seen, grid_cell)
        VALUES (:id, :name, :lat, :lng, :type, :cuisine, :brand, :source, :source_id, 
                :rating, :price, :addr, :city, :state, :zip, :phone, :web, :updated, :first, :cell)
        ON CONFLICT(id) DO UPDATE SET
        name = excluded.name, lat = excluded.lat, lng = excluded.lng, type = excluded.type,
        cuisine = excluded.cuisine, brand = excluded.brand, rating = excluded.rating,
        price_level = excluded.price_level, address = excluded.address, phone = excluded.phone,
        website = excluded.website, last_updated = excluded.last_updated, check_count = check_count + 1');
    
    foreach ($uniqueVenues as $v) {
        $stmt->bindValue(':id', $v['id']);
        $stmt->bindValue(':name', $v['name']);
        $stmt->bindValue(':lat', $v['lat']);
        $stmt->bindValue(':lng', $v['lng']);
        $stmt->bindValue(':type', $v['type']);
        $stmt->bindValue(':cuisine', $v['cuisine']);
        $stmt->bindValue(':brand', $v['brand']);
        $stmt->bindValue(':source', $v['source']);
        $stmt->bindValue(':source_id', $v['source_id']);
        $stmt->bindValue(':rating', $v['rating']);
        $stmt->bindValue(':price', $v['price_level']);
        $stmt->bindValue(':addr', $v['address']);
        $stmt->bindValue(':city', $v['city']);
        $stmt->bindValue(':state', $v['state']);
        $stmt->bindValue(':zip', $v['zip']);
        $stmt->bindValue(':phone', $v['phone']);
        $stmt->bindValue(':web', $v['website']);
        $stmt->bindValue(':updated', $now);
        $stmt->bindValue(':first', $now);
        $stmt->bindValue(':cell', $cellKey);
        $stmt->execute();
        $inserted++;
    }
    
    // Update grid cell record
    updateGridCell($db, $cellKey, $uniqueVenues);
    
    logMessage("  Inserted/updated: $inserted venues");
}

// Main execution
$force = in_array('--force', $argv);
$specificCell = null;

foreach ($argv as $arg) {
    if (preg_match('/^-?\d+\.\d+,-?\d+\.\d+$/', $arg)) {
        $specificCell = $arg;
        break;
    }
}

logMessage("=== Neutral Eats Data Ingestion Started ===");

$db = initDatabase($dbPath);

if ($specificCell) {
    ingestGridCell($db, $specificCell, $force);
} else {
    foreach ($orlandoGridCells as $cell) {
        ingestGridCell($db, $cell, $force);
        sleep(2); // Be nice to APIs
    }
}

logMessage("=== Ingestion Complete ===");
?>