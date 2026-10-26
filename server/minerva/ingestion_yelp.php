#!/usr/bin/env php
<?php
/**
 * Neutral Eats - Yelp Fusion Ingestion
 * Targets low-coverage areas (Orlando priority)
 */

$dbHost = 'localhost';
$dbName = 'neutraleats';
$dbUser = 'neutraleats_user';
$dbPass = 'neutraleats_pass';
$YELP_API_KEY = 'REDACTED';

$lastYelpCall = 0;
$YELP_RATE_LIMIT = 0.02; // ~50 calls/second max, be conservative

function log_msg($msg) {
    $ts = date('Y-m-d H:i:s');
    echo "[$ts] $msg\n";
    file_put_contents('/var/www/html/minerva/data/yelp_ingestion.log', "[$ts] $msg\n", FILE_APPEND);
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
    global $lastYelpCall, $YELP_RATE_LIMIT;
    $elapsed = microtime(true) - $lastYelpCall;
    if ($elapsed < $YELP_RATE_LIMIT) {
        usleep(($YELP_RATE_LIMIT - $elapsed) * 1000000);
    }
    $lastYelpCall = microtime(true);
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
            (id, name, lat, lng, type, cuisine, brand, address, phone, website, source, source_id, rating, price_level, first_seen, is_active) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
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
            $venue['rating'] ?? null,
            $venue['price_level'] ?? null,
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
    if (strpos($cat, 'cafe') !== false || strpos($cat, 'coffee') !== false) {
        return 'cafe';
    } elseif (strpos($cat, 'bar') !== false || strpos($cat, 'pub') !== false) {
        return 'bar';
    } elseif (strpos($cat, 'fast') !== false) {
        return 'fast_food';
    }
    return 'restaurant';
}

function fetchYelp($lat, $lng, $radius = 2000) {
    global $YELP_API_KEY;
    rateLimit();
    
    $url = "https://api.yelp.com/v3/businesses/search";
    $headers = ["Authorization: Bearer $YELP_API_KEY"];
    $params = [
        'latitude' => $lat,
        'longitude' => $lng,
        'radius' => $radius,
        'categories' => 'restaurants,food,cafes,bars',
        'limit' => 50,
        'sort_by' => 'best_match'
    ];
    
    $ch = curl_init($url . '?' . http_build_query($params));
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_HTTPHEADER, $headers);
    curl_setopt($ch, CURLOPT_TIMEOUT, 30);
    $response = curl_exec($ch);
    $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);
    
    if ($httpCode !== 200 || !$response) {
        log_msg("Yelp API error: HTTP $httpCode");
        return [];
    }
    
    $data = json_decode($response, true);
    if (!$data || !isset($data['businesses'])) {
        log_msg("Yelp: Invalid response");
        return [];
    }
    
    $venues = [];
    foreach ($data['businesses'] as $biz) {
        $coords = $biz['coordinates'] ?? [];
        $cats = $biz['categories'] ?? [];
        $catNames = array_column($cats, 'title');
        
        $venues[] = [
            'name' => $biz['name'],
            'lat' => $coords['latitude'] ?? 0,
            'lng' => $coords['longitude'] ?? 0,
            'type' => categorizeType(implode(' ', $catNames)),
            'cuisine' => implode(', ', $catNames),
            'brand' => '',
            'rating' => $biz['rating'] ?? null,
            'price_level' => strlen($biz['price'] ?? ''),
            'address' => implode(', ', $biz['location']['display_address'] ?? []),
            'phone' => $biz['phone'] ?? '',
            'website' => $biz['url'] ?? '',
            'source' => 'yelp',
            'source_id' => $biz['id']
        ];
    }
    
    log_msg("Yelp: Found " . count($venues) . " venues near $lat,$lng");
    return $venues;
}

// ORLANDO PRIORITY GRID - Dense coverage
$orlandoGrid = [
    // Downtown core
    [28.540, -81.380], [28.545, -81.375], [28.535, -81.385],
    // Winter Park
    [28.600, -81.350], [28.595, -81.345], [28.605, -81.355],
    // Dr Phillips / I-Drive
    [28.430, -81.470], [28.435, -81.465], [28.425, -81.475],
    // UCF area
    [28.600, -81.200], [28.595, -81.195], [28.605, -81.205],
    // Kissimmee
    [28.300, -81.420], [28.295, -81.415], [28.305, -81.425],
    // Altamonte
    [28.660, -81.370], [28.655, -81.365],
    // Windermere
    [28.490, -81.530], [28.485, -81.525],
];

log_msg("=" . str_repeat("=", 60));
log_msg("Starting YELP Orlando Priority Ingestion");
log_msg("Grid points: " . count($orlandoGrid));
log_msg("=" . str_repeat("=", 60));

$pdo = getDB();
if (!$pdo) {
    log_msg("Failed to connect to database");
    exit(1);
}

$totalAdded = 0;
$apiCalls = 0;

foreach ($orlandoGrid as $i => $point) {
    list($lat, $lng) = $point;
    log_msg("\n[" . ($i + 1) . "/" . count($orlandoGrid) . "] Querying Yelp: $lat,$lng");
    
    $venues = fetchYelp($lat, $lng, 2000);
    $apiCalls++;
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
    
    // Progress
    if (($i + 1) % 5 == 0) {
        log_msg("PROGRESS: " . ($i + 1) . "/" . count($orlandoGrid) . " points, $totalAdded venues added");
    }
}

log_msg("\n" . str_repeat("=", 60));
log_msg("YELP INGESTION COMPLETE!");
log_msg("API calls made: $apiCalls");
log_msg("Total new venues added: $totalAdded");
log_msg(str_repeat("=", 60));
