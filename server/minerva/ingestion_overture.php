#!/usr/bin/env php
<?php
/**
 * Neutral Eats - Overture Maps Ingestion Script
 * PHP version (no extra dependencies needed)
 * 
 * Usage: php ingestion_overture.php
 */

// Database configuration
$dbHost = 'localhost';
$dbName = 'neutraleats';
$dbUser = 'neutraleats_user';
$dbPass = 'neutraleats_pass';

// Rate limiting
$lastOvertureCall = 0;
$OVERTURE_RATE_LIMIT = 0.5; // 2 calls per second

// Logging
function log_msg($msg) {
    $ts = date('Y-m-d H:i:s');
    echo "[$ts] $msg\n";
    file_put_contents('/var/www/html/minerva/data/ingestion.log', "[$ts] $msg\n", FILE_APPEND);
}

// Database connection
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

// Rate limiting
function rateLimit($source) {
    global $lastOvertureCall, $OVERTURE_RATE_LIMIT;
    
    if ($source === 'overture') {
        $elapsed = microtime(true) - $lastOvertureCall;
        if ($elapsed < $OVERTURE_RATE_LIMIT) {
            usleep(($OVERTURE_RATE_LIMIT - $elapsed) * 1000000);
        }
        $lastOvertureCall = microtime(true);
    }
}

// Check if venue exists (name + address deduplication)
function venueExists($pdo, $name, $address, $lat, $lng) {
    // Normalize
    $normAddress = strtolower(trim($address));
    
    // Check 1: Same name + same address
    if ($normAddress) {
        $stmt = $pdo->prepare("SELECT id FROM venues WHERE LOWER(name) = LOWER(?) AND LOWER(address) = LOWER(?) LIMIT 1");
        $stmt->execute([$name, $address]);
        if ($stmt->fetch()) return true;
    }
    
    // Check 2: Same name within 100m
    $stmt = $pdo->prepare("SELECT id FROM venues WHERE LOWER(name) = LOWER(?) AND ABS(lat - ?) < 0.001 AND ABS(lng - ?) < 0.001 LIMIT 1");
    $stmt->execute([$name, $lat, $lng]);
    if ($stmt->fetch()) return true;
    
    return false;
}

// Insert venue
function insertVenue($pdo, $venue) {
    try {
        // Generate unique ID from source + source_id
        $id = $venue['source'] . ':' . ($venue['source_id'] ?? uniqid());
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

// Categorize venue type
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

// Format address
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

// Fetch from Overture
function fetchOverture($west, $south, $east, $north) {
    rateLimit('overture');
    
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
        
        // Skip non-food venues
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

// Central Florida Priority Grid
$grid = [
    [-81.45, 28.50, -81.35, 28.60],  // Downtown/Dr Phillips
    [-81.35, 28.50, -81.25, 28.60],  // Winter Park
    [-81.25, 28.50, -81.15, 28.60],  // UCF/East Orlando
    [-81.45, 28.40, -81.35, 28.50],  // International Drive
    [-81.35, 28.40, -81.25, 28.50],  // Airport/South Orlando
    [-81.50, 28.60, -81.40, 28.70],  // North Orlando
    [-81.60, 28.30, -81.50, 28.40],  // Disney/Kissimmee
    [-81.50, 28.30, -81.40, 28.40],  // Kissimmee East
    [-81.40, 28.70, -81.30, 28.80],  // Altamonte/Lake Mary
    [-81.30, 28.60, -81.20, 28.70],  // Oviedo
    [-81.70, 28.40, -81.60, 28.50],  // Windermere
    [-81.60, 28.50, -81.50, 28.60],  // Ocoee
];

// Main ingestion
log_msg("=" . str_repeat("=", 50));
log_msg("Starting Central Florida Overture Ingestion");
log_msg("=" . str_repeat("=", 50));

$pdo = getDB();
if (!$pdo) {
    log_msg("Failed to connect to database");
    exit(1);
}

$totalAdded = 0;
foreach ($grid as $i => $bbox) {
    list($west, $south, $east, $north) = $bbox;
    log_msg("[" . ($i + 1) . "/" . count($grid) . "] Processing area: $west,$south,$east,$north");
    
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
}

log_msg("=" . str_repeat("=", 50));
log_msg("Ingestion complete! Total added: $totalAdded");
log_msg("=" . str_repeat("=", 50));
