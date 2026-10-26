#!/usr/bin/env php
<?php
/**
 * Neutral Eats - Florida Statewide Overture Ingestion
 * Expanded coverage: All major metros and suburbs
 */

$dbHost = 'localhost';
$dbName = 'neutraleats';
$dbUser = 'neutraleats_user';
$dbPass = 'neutraleats_pass';

$lastOvertureCall = 0;
$OVERTURE_RATE_LIMIT = 0.5;

function log_msg($msg) {
    $ts = date('Y-m-d H:i:s');
    echo "[$ts] $msg\n";
    file_put_contents('/var/www/html/minerva/data/statewide_ingestion.log', "[$ts] $msg\n", FILE_APPEND);
}

function getDB() {
    global $dbHost, $dbName, $dbUser, $dbPass;
    try {
        $pdo = new PDO("mysql:host=$dbHost;dbname=$dbName;charset=utf8mb4", $dbUser, $dbPass);
        $pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
        return $pdo;
    } catch (PDOException $e) {
        log_msg("Database connection failed: " . $e->getMessage());
        return null;
    }
}

function rateLimit() {
    global $lastOvertureCall, $OVERTURE_RATE_LIMIT;
    $elapsed = microtime(true) - $lastOvertureCall;
    if ($elapsed < $OVERTURE_RATE_LIMIT) {
        usleep(($OVERTURE_RATE_LIMIT - $elapsed) * 1000000);
    }
    $lastOvertureCall = microtime(true);
}

function venueExists($pdo, $name, $address, $lat, $lng) {
    $normAddress = strtolower(trim($address));
    
    if ($normAddress) {
        $stmt = $pdo->prepare("SELECT id FROM venues WHERE LOWER(name) = LOWER(?) AND LOWER(address) = LOWER(?) LIMIT 1");
        $stmt->execute([$name, $address]);
        if ($stmt->fetch()) return true;
    }
    
    $stmt = $pdo->prepare("SELECT id FROM venues WHERE LOWER(name) = LOWER(?) AND ABS(lat - ?) < 0.001 AND ABS(lng - ?) < 0.001 LIMIT 1");
    $stmt->execute([$name, $lat, $lng]);
    if ($stmt->fetch()) return true;
    
    return false;
}

function insertVenue($pdo, $venue) {
    try {
        $id = $venue['source'] . ':' . ($venue['source_id'] ?: uniqid());
        $firstSeen = time();
        
        $stmt = $pdo->prepare("INSERT INTO venues 
            (id, name, lat, lng, type, cuisine, brand, address, phone, website, source, source_id, first_seen, is_active) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            ON DUPLICATE KEY UPDATE 
                rating = VALUES(rating), 
                price_level = VALUES(price_level),
                last_updated = NOW()");
        
        $stmt->execute([
            $id,
            $venue['name'] ?? 'Unknown',
            $venue['lat'],
            $venue['lng'],
            $venue['type'] ?? 'restaurant',
            $venue['cuisine'] ?? '',
            $venue['brand'] ?? '',
            $venue['address'] ?? '',
            $venue['phone'] ?? '',
            $venue['website'] ?? '',
            $venue['source'],
            $venue['source_id'] ?? '',
            $firstSeen
        ]);
        return true;
    } catch (PDOException $e) {
        log_msg("Insert failed: " . $e->getMessage());
        return false;
    }
}

function categorizeType($category) {
    $cat = strtolower($category);
    if (strpos($cat, 'cafe') !== false || strpos($cat, 'coffee') !== false || strpos($cat, 'bakery') !== false) {
        return 'cafe';
    } elseif (strpos($cat, 'bar') !== false || strpos($cat, 'pub') !== false) {
        return 'bar';
    } elseif (strpos($cat, 'fast') !== false) {
        return 'fast_food';
    }
    return 'restaurant';
}

function formatAddress($addr) {
    if (!$addr) return '';
    $parts = [
        $addr['street'] ?? '',
        $addr['city'] ?? '',
        $addr['region'] ?? '',
        $addr['postcode'] ?? ''
    ];
    return implode(', ', array_filter($parts));
}

function fetchOverture($west, $south, $east, $north) {
    rateLimit();
    
    $url = "https://www.fused.io/server/v1/realtime-shared/UDF_Overture_Maps_Example/run/file";
    $params = [
        'bbox' => "$west,$south,$east,$north",
        'overture_type' => 'place',
        'format' => 'geojson'
    ];
    
    $ch = curl_init($url . '?' . http_build_query($params));
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_TIMEOUT, 30);
    $response = curl_exec($ch);
    $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);
    
    if ($httpCode !== 200 || !$response) {
        log_msg("Overture API error: HTTP $httpCode");
        return [];
    }
    
    $data = json_decode($response, true);
    if (!$data || !isset($data['features'])) {
        log_msg("Overture: Invalid response");
        return [];
    }
    
    $venues = [];
    foreach ($data['features'] as $feature) {
        $props = $feature['properties'] ?? [];
        $coords = $feature['geometry']['coordinates'] ?? [0, 0];
        
        $category = strtolower($props['categories']['primary'] ?? '');
        $foodTerms = ['restaurant', 'food', 'cafe', 'bar', 'pub', 'bakery', 'coffee'];
        $isFood = false;
        foreach ($foodTerms as $term) {
            if (strpos($category, $term) !== false) {
                $isFood = true;
                break;
            }
        }
        if (!$isFood) continue;
        
        $venues[] = [
            'name' => $props['names']['primary'] ?? 'Unknown',
            'lat' => $coords[1],
            'lng' => $coords[0],
            'type' => categorizeType($category),
            'cuisine' => '',
            'brand' => $props['brand']['names']['primary'] ?? '',
            'address' => formatAddress($props['addresses'][0] ?? []),
            'phone' => $props['phone'] ?? '',
            'website' => is_array($props['websites'] ?? []) ? ($props['websites'][0] ?? '') : '',
            'source' => 'overture',
            'source_id' => $props['id'] ?? '',
            'raw_data' => $props
        ];
    }
    
    log_msg("Overture: Found " . count($venues) . " venues");
    return $venues;
}

// FLORIDA STATEWIDE GRID - Comprehensive coverage
$floridaGrid = [
    // Orlando Metro (expanded)
    [-81.45, 28.50, -81.35, 28.60], [-81.35, 28.50, -81.25, 28.60],
    [-81.25, 28.50, -81.15, 28.60], [-81.45, 28.40, -81.35, 28.50],
    [-81.35, 28.40, -81.25, 28.50], [-81.50, 28.60, -81.40, 28.70],
    [-81.60, 28.30, -81.50, 28.40], [-81.50, 28.30, -81.40, 28.40],
    [-81.40, 28.70, -81.30, 28.80], [-81.30, 28.60, -81.20, 28.70],
    [-81.70, 28.40, -81.60, 28.50], [-81.60, 28.50, -81.50, 28.60],
    
    // Tampa Bay (expanded)
    [-82.50, 27.90, -82.40, 28.00], [-82.70, 27.90, -82.60, 28.00],
    [-82.40, 27.90, -82.30, 28.00], [-82.70, 27.70, -82.60, 27.80],
    [-82.60, 27.70, -82.50, 27.80], [-82.80, 27.90, -82.70, 28.00],
    [-82.50, 27.80, -82.40, 27.90], [-82.40, 27.80, -82.30, 27.90],
    
    // Miami / Fort Lauderdale (expanded)
    [-80.20, 25.70, -80.10, 25.80], [-80.10, 25.70, -80.00, 25.80],
    [-80.30, 25.70, -80.20, 25.80], [-80.20, 25.60, -80.10, 25.70],
    [-80.10, 25.60, -80.00, 25.70], [-80.00, 25.60, -79.90, 25.70],
    [-80.15, 25.80, -80.05, 25.90], [-80.25, 26.10, -80.15, 26.20],
    
    // Jacksonville
    [-81.70, 30.30, -81.60, 30.40], [-81.60, 30.30, -81.50, 30.40],
    [-81.50, 30.30, -81.40, 30.40], [-81.70, 30.20, -81.60, 30.30],
    
    // Gainesville
    [-82.35, 29.65, -82.25, 29.75], [-82.45, 29.65, -82.35, 29.75],
    
    // Tallahassee
    [-84.35, 30.45, -84.25, 30.55], [-84.25, 30.45, -84.15, 30.55],
    
    // Naples / Fort Myers
    [-81.80, 26.15, -81.70, 26.25], [-81.90, 26.55, -81.80, 26.65],
    [-81.80, 26.55, -81.70, 26.65], [-81.70, 26.55, -81.60, 26.65],
    
    // Sarasota / Bradenton
    [-82.60, 27.35, -82.50, 27.45], [-82.50, 27.35, -82.40, 27.45],
    
    // West Palm Beach
    [-80.10, 26.70, -80.00, 26.80], [-80.00, 26.70, -79.90, 26.80],
    
    // Daytona Beach
    [-81.05, 29.20, -80.95, 29.30], [-80.95, 29.20, -80.85, 29.30],
    
    // Pensacola
    [-87.25, 30.40, -87.15, 30.50], [-87.15, 30.40, -87.05, 30.50],
    
    // Panama City
    [-85.70, 30.15, -85.60, 30.25], [-85.60, 30.15, -85.50, 30.25],
];

// Main ingestion
log_msg("=" . str_repeat("=", 60));
log_msg("Starting FLORIDA STATEWIDE Overture Ingestion");
log_msg("Total grid cells: " . count($floridaGrid));
log_msg("=" . str_repeat("=", 60));

$pdo = getDB();
if (!$pdo) {
    log_msg("Failed to connect to database");
    exit(1);
}

$totalAdded = 0;
$cellCount = 0;

foreach ($floridaGrid as $bbox) {
    $cellCount++;
    list($west, $south, $east, $north) = $bbox;
    log_msg("\n[$cellCount/" . count($floridaGrid) . "] Processing: $west,$south,$east,$north");
    
    $venues = fetchOverture($west, $south, $east, $north);
    $added = 0;
    
    foreach ($venues as $venue) {
        if (!venueExists($pdo, $venue['name'], $venue['address'], $venue['lat'], $venue['lng'])) {
            if (insertVenue($pdo, $venue)) {
                $added++;
                $totalAdded++;
            }
        }
    }
    
    log_msg("Added $added new venues (total: $totalAdded)");
    
    // Progress every 5 cells
    if ($cellCount % 5 == 0) {
        log_msg("PROGRESS: $cellCount/" . count($floridaGrid) . " cells completed");
    }
}

log_msg("\n" . str_repeat("=", 60));
log_msg("STATEWIDE INGESTION COMPLETE!");
log_msg("Total new venues added: $totalAdded");
log_msg(str_repeat("=", 60));
