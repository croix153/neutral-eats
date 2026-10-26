#!/usr/bin/env php
<?php
/**
 * Neutral Eats - NATIONWIDE US Yelp Ingestion
 * Covers all major metros with smart grid distribution
 * Respects 5,000 daily API limit
 */

$dbHost = 'localhost';
$dbName = 'neutraleats';
$dbUser = 'neutraleats_user';
$dbPass = 'neutraleats_pass';
$YELP_API_KEY = 'REDACTED';

$lastYelpCall = 0;
$YELP_RATE_LIMIT = 0.02; // Conservative: ~50 calls/sec max
$DAILY_LIMIT = 4900; // Leave buffer below 5k

function log_msg($msg) {
    $ts = date('Y-m-d H:i:s');
    echo "[$ts] $msg\n";
    file_put_contents('/var/www/html/minerva/data/nationwide_yelp.log', "[$ts] $msg\n", FILE_APPEND);
}

function getDB() {
    global $dbHost, $dbName, $dbUser, $dbPass;
    try {
        $pdo = new PDO("mysql:host=$dbHost;dbname=$dbName;charset=utf8mb4", $dbUser, $dbPass);
        $pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
        return $pdo;
    } catch (PDOException $e) {
        log_msg("DB connection failed: " . $e->getMessage());
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
    return $stmt->fetch() !== false;
}

function insertVenue($pdo, $venue) {
    try {
        $id = 'yelp:' . $venue['source_id'];
        $stmt = $pdo->prepare("INSERT INTO venues 
            (id, name, lat, lng, type, cuisine, brand, address, phone, website, source, source_id, rating, price_level, first_seen, is_active) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            ON DUPLICATE KEY UPDATE rating = VALUES(rating), price_level = VALUES(price_level), last_updated = NOW()");
        
        $stmt->execute([
            $id, $venue['name'], $venue['lat'], $venue['lng'], 
            $venue['type'] ?? 'restaurant', $venue['cuisine'] ?? '', $venue['brand'] ?? '',
            $venue['address'] ?? '', $venue['phone'] ?? '', $venue['website'] ?? '',
            'yelp', $venue['source_id'], $venue['rating'] ?? null, $venue['price_level'] ?? null,
            time()
        ]);
        return true;
    } catch (PDOException $e) {
        log_msg("Insert failed: " . $e->getMessage());
        return false;
    }
}

function categorizeType($category) {
    $cat = strtolower($category);
    if (strpos($cat, 'cafe') !== false || strpos($cat, 'coffee') !== false) return 'cafe';
    if (strpos($cat, 'bar') !== false || strpos($cat, 'pub') !== false) return 'bar';
    if (strpos($cat, 'fast') !== false) return 'fast_food';
    return 'restaurant';
}

function fetchYelp($lat, $lng, $radius = 2000) {
    global $YELP_API_KEY;
    rateLimit();
    
    $ch = curl_init("https://api.yelp.com/v3/businesses/search?" . http_build_query([
        'latitude' => $lat, 'longitude' => $lng, 'radius' => $radius,
        'categories' => 'restaurants,food,cafes,bars', 'limit' => 50, 'sort_by' => 'best_match'
    ]));
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_HTTPHEADER, ["Authorization: Bearer $YELP_API_KEY"]);
    curl_setopt($ch, CURLOPT_TIMEOUT, 30);
    $response = curl_exec($ch);
    $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);
    
    if ($httpCode !== 200 || !$response) {
        log_msg("Yelp API error: HTTP $httpCode");
        return [];
    }
    
    $data = json_decode($response, true);
    if (!$data || !isset($data['businesses'])) return [];
    
    $venues = [];
    foreach ($data['businesses'] as $biz) {
        $cats = array_column($biz['categories'] ?? [], 'title');
        $venues[] = [
            'name' => $biz['name'],
            'lat' => $biz['coordinates']['latitude'] ?? 0,
            'lng' => $biz['coordinates']['longitude'] ?? 0,
            'type' => categorizeType(implode(' ', $cats)),
            'cuisine' => implode(', ', $cats),
            'rating' => $biz['rating'] ?? null,
            'price_level' => strlen($biz['price'] ?? ''),
            'address' => implode(', ', $biz['location']['display_address'] ?? []),
            'phone' => $biz['phone'] ?? '',
            'website' => $biz['url'] ?? '',
            'source_id' => $biz['id']
        ];
    }
    return $venues;
}

// MAJOR US METROS - Priority order (population + food scene)
$usMetros = [
    // FLORIDA (already done, but included for completeness)
    ['Orlando, FL', 28.540, -81.380], ['Tampa, FL', 27.950, -82.460], ['Miami, FL', 25.770, -80.190],
    ['Jacksonville, FL', 30.330, -81.660], ['Tallahassee, FL', 30.440, -84.280],
    
    // TEXAS (huge food scene)
    ['Houston, TX', 29.760, -95.370], ['Dallas, TX', 32.780, -96.800], ['Austin, TX', 30.270, -97.740],
    ['San Antonio, TX', 29.420, -98.490], ['Fort Worth, TX', 32.750, -97.330],
    
    // CALIFORNIA (massive market)
    ['Los Angeles, CA', 34.050, -118.240], ['San Diego, CA', 32.710, -117.160], ['San Francisco, CA', 37.770, -122.420],
    ['San Jose, CA', 37.330, -121.890], ['Sacramento, CA', 38.580, -121.490], ['Oakland, CA', 37.800, -122.270],
    
    // NEW YORK / TRI-STATE
    ['New York, NY', 40.710, -74.010], ['Brooklyn, NY', 40.650, -73.950], ['Queens, NY', 40.750, -73.800],
    ['Bronx, NY', 40.850, -73.870], ['Staten Island, NY', 40.580, -74.150],
    
    // MIDWEST
    ['Chicago, IL', 41.880, -87.630], ['Detroit, MI', 42.330, -83.050], ['Cleveland, OH', 41.500, -81.690],
    ['Columbus, OH', 39.960, -83.000], ['Cincinnati, OH', 39.100, -84.510], ['Indianapolis, IN', 39.770, -86.150],
    ['Milwaukee, WI', 43.040, -87.910], ['St. Louis, MO', 38.630, -90.200], ['Kansas City, MO', 39.100, -94.580],
    ['Minneapolis, MN', 44.980, -93.270], ['St. Paul, MN', 44.950, -93.090],
    
    // SOUTHEAST
    ['Atlanta, GA', 33.750, -84.390], ['Charlotte, NC', 35.230, -80.840], ['Raleigh, NC', 35.780, -78.640],
    ['Nashville, TN', 36.160, -86.780], ['Memphis, TN', 35.150, -90.050], ['New Orleans, LA', 29.950, -90.070],
    ['Birmingham, AL', 33.520, -86.800], ['Louisville, KY', 38.250, -85.760],
    
    // NORTHEAST
    ['Philadelphia, PA', 39.950, -75.170], ['Pittsburgh, PA', 40.440, -80.000], ['Baltimore, MD', 39.290, -76.610],
    ['Washington, DC', 38.910, -77.020], ['Boston, MA', 42.360, -71.060], ['Providence, RI', 41.820, -71.410],
    ['Hartford, CT', 41.760, -72.680], ['New Haven, CT', 41.310, -72.920],
    ['Buffalo, NY', 42.880, -78.880], ['Rochester, NY', 43.160, -77.610], ['Albany, NY', 42.650, -73.760],
    ['Newark, NJ', 40.730, -74.170], ['Jersey City, NJ', 40.720, -74.040],
    
    // SOUTHWEST
    ['Phoenix, AZ', 33.450, -112.070], ['Tucson, AZ', 32.220, -110.970], ['Las Vegas, NV', 36.170, -115.140],
    ['Albuquerque, NM', 35.080, -106.650], ['El Paso, TX', 31.760, -106.490],
    
    // NORTHWEST
    ['Seattle, WA', 47.610, -122.330], ['Portland, OR', 45.520, -122.680], ['Denver, CO', 39.740, -104.990],
    ['Boise, ID', 43.620, -116.210], ['Salt Lake City, UT', 40.760, -111.890],
    
    // SOUTHERN CALIFORNIA
    ['Riverside, CA', 33.950, -117.390], ['Anaheim, CA', 33.840, -117.910], ['Santa Ana, CA', 33.740, -117.870],
    ['Bakersfield, CA', 35.370, -119.020], ['Fresno, CA', 36.740, -119.790], ['Long Beach, CA', 33.770, -118.190],
    
    // OTHER MAJOR
    ['Oklahoma City, OK', 35.470, -97.520], ['Tulsa, OK', 36.150, -95.990], ['Omaha, NE', 41.260, -95.940],
    ['Wichita, KS', 37.690, -97.330], ['Colorado Springs, CO', 38.830, -104.820],
    ['Honolulu, HI', 21.310, -157.860], ['Anchorage, AK', 61.220, -149.900],
    
    // CANADA 🍁 (because Croix said "fuck it, and canada!")
    ['Toronto, ON', 43.650, -79.380], ['Montreal, QC', 45.500, -73.570], ['Vancouver, BC', 49.280, -123.120],
    ['Calgary, AB', 51.050, -114.070], ['Ottawa, ON', 45.420, -75.700], ['Edmonton, AB', 53.540, -113.490],
    ['Quebec City, QC', 46.810, -71.210], ['Winnipeg, MB', 49.900, -97.140], ['Hamilton, ON', 43.250, -79.870],
    ['Kitchener, ON', 43.450, -80.490], ['London, ON', 42.980, -81.250], ['Victoria, BC', 48.430, -123.370],
    ['Halifax, NS', 44.650, -63.580], ['Saskatoon, SK', 52.130, -106.670], ['St. Catharines, ON', 43.160, -79.240],
];

log_msg("=" . str_repeat("=", 70));
log_msg("NATIONWIDE US/CANADA YELP INGESTION - Phase 1: Major Metros");
log_msg("Total metros: " . count($usMetros));
log_msg("Daily API limit: ~$DAILY_LIMIT calls");
log_msg("🍁 INCLUDING CANADA!");
log_msg("=" . str_repeat("=", 70));

$pdo = getDB();
if (!$pdo) {
    log_msg("Failed to connect to database");
    exit(1);
}

// Load progress from state file
$stateFile = '/var/www/html/minerva/data/nationwide_state.json';
$state = ['last_index' => 0, 'total_added' => 0, 'api_calls' => 0];
if (file_exists($stateFile)) {
    $state = json_decode(file_get_contents($stateFile), true) ?: $state;
}

$totalAdded = $state['total_added'];
$apiCalls = $state['api_calls'];
$startIndex = $state['last_index'];

log_msg("Resuming from metro #$startIndex");
log_msg("Previous total: $totalAdded venues added");
log_msg("API calls so far today: $apiCalls");

for ($i = $startIndex; $i < count($usMetros); $i++) {
    if ($apiCalls >= $DAILY_LIMIT) {
        log_msg("\n⚠️ DAILY API LIMIT REACHED ($apiCalls calls)");
        log_msg("Stopping for today. Resume tomorrow to continue.");
        break;
    }
    
    $metro = $usMetros[$i];
    list($name, $lat, $lng) = $metro;
    
    log_msg("\n[" . ($i + 1) . "/" . count($usMetros) . "] Processing: $name");
    
    // 3-point grid per metro for better coverage
    $points = [
        [$lat, $lng],           // Center
        [$lat + 0.02, $lng],    // North
        [$lat - 0.02, $lng],    // South
        [$lat, $lng + 0.02],    // East
        [$lat, $lng - 0.02],    // West
    ];
    
    $metroAdded = 0;
    foreach ($points as $point) {
        if ($apiCalls >= $DAILY_LIMIT) break;
        
        $venues = fetchYelp($point[0], $point[1], 2500);
        $apiCalls++;
        
        foreach ($venues as $venue) {
            if (!venueExists($pdo, $venue['name'], $venue['address'], $venue['lat'], $venue['lng'])) {
                if (insertVenue($pdo, $venue)) {
                    $metroAdded++;
                    $totalAdded++;
                }
            }
        }
        
        // Small delay between points
        usleep(100000); // 100ms
    }
    
    log_msg("Added $metroAdded venues from $name (total: $totalAdded)");
    
    // Save progress
    $state = ['last_index' => $i + 1, 'total_added' => $totalAdded, 'api_calls' => $apiCalls];
    file_put_contents($stateFile, json_encode($state));
    
    // Progress every 5 metros
    if (($i + 1) % 5 == 0) {
        log_msg("PROGRESS: " . ($i + 1) . "/" . count($usMetros) . " metros, $totalAdded total venues, $apiCalls API calls");
    }
}

log_msg("\n" . str_repeat("=", 70));
log_msg("NATIONWIDE INGESTION PAUSED/COMPLETE");
log_msg("Total metros processed: $i/" . count($usMetros));
log_msg("Total new venues: $totalAdded");
log_msg("Total API calls: $apiCalls");
log_msg("Progress saved. Resume anytime to continue.");
log_msg(str_repeat("=", 70));
