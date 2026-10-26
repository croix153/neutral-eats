<?php
/**
 * Florida Restaurant Ingestion - Google Places API Version
 * Populates database with restaurants from 61 Florida areas
 */

// Configuration
$dbHost = 'localhost';
$dbName = 'neutraleats';
$dbUser = 'neutraleats_user';
$dbPass = 'neutraleats_pass';

// Google Places API Key - Free tier: $300 credit
// Get from: https://developers.google.com/maps/documentation/places/web-service/get-api-key
$googleApiKey = getenv('GOOGLE_PLACES_API_KEY') ?: 'YOUR_API_KEY_HERE';

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

$radiusMeters = 10000; // 10km radius per query
$type = 'restaurant'; // Google Places type

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

/**
 * Fetch restaurants from Google Places API (Nearby Search)
 */
function fetchGooglePlaces($lat, $lng, $radius, $type, $apiKey, $pageToken = null) {
    if ($apiKey === 'YOUR_API_KEY_HERE') {
        logMessage("ERROR: Google Places API key not configured!");
        return ['results' => [], 'next_page_token' => null];
    }
    
    if ($pageToken) {
        $url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json?pagetoken=" . urlencode($pageToken) . "&key=" . urlencode($apiKey);
    } else {
        $url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json?location=" . urlencode("$lat,$lng") . "&radius=" . urlencode($radius) . "&type=" . urlencode($type) . "&key=" . urlencode($apiKey);
    }
    
    $ch = curl_init($url);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_TIMEOUT, 30);
    curl_setopt($ch, CURLOPT_FOLLOWLOCATION, true);
    curl_setopt($ch, CURLOPT_USERAGENT, 'NeutralEatsBot/1.0');
    
    $response = curl_exec($ch);
    $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);
    
    if ($httpCode !== 200 || !$response) {
        logMessage("  HTTP Error: $httpCode");
        return ['results' => [], 'next_page_token' => null];
    }
    
    $data = json_decode($response, true);
    
    if (isset($data['error_message'])) {
        logMessage("  Google API Error: " . $data['error_message']);
    }
    
    return [
        'results' => $data['results'] ?? [],
        'next_page_token' => $data['next_page_token'] ?? null,
        'status' => $data['status'] ?? 'UNKNOWN'
    ];
}

/**
 * Get place details including address_components
 */
function getPlaceDetails($placeId, $apiKey) {
    if ($apiKey === 'YOUR_API_KEY_HERE') {
        return null;
    }
    
    $url = "https://maps.googleapis.com/maps/api/place/details/json?place_id=" . urlencode($placeId) . "&fields=address_components,formatted_address&key=" . urlencode($apiKey);
    
    $ch = curl_init($url);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_TIMEOUT, 30);
    curl_setopt($ch, CURLOPT_USERAGENT, 'NeutralEatsBot/1.0');
    
    $response = curl_exec($ch);
    curl_close($ch);
    
    if (!$response) return null;
    
    $data = json_decode($response, true);
    return $data['result'] ?? null;
}

/**
 * Extract city from address_components
 */
function extractCity($addressComponents) {
    if (!$addressComponents) return '';
    
    foreach ($addressComponents as $component) {
        $types = $component['types'] ?? [];
        
        // Look for locality (city) first
        if (in_array('locality', $types)) {
            return $component['long_name'] ?? '';
        }
        
        // Fallback to postal_town
        if (in_array('postal_town', $types)) {
            return $component['long_name'] ?? '';
        }
        
        // Fallback to administrative_area_level_2 (county)
        if (in_array('administrative_area_level_2', $types) && empty($city)) {
            $city = $component['long_name'] ?? '';
        }
    }
    
    return $city ?? '';
}

/**
 * Parse Google Places results into venue format
 */
function parseGooglePlaces($places, $defaultCity, $apiKey) {
    $venues = [];
    
    foreach ($places as $place) {
        $placeId = $place['place_id'] ?? null;
        if (!$placeId) continue;
        
        $name = $place['name'] ?? 'Unnamed';
        $lat = $place['geometry']['location']['lat'] ?? 0;
        $lng = $place['geometry']['location']['lng'] ?? 0;
        
        // Determine type
        $types = $place['types'] ?? [];
        $type = 'restaurant';
        if (in_array('cafe', $types) || in_array('bakery', $types)) {
            $type = 'cafe';
        } elseif (in_array('bar', $types) || in_array('night_club', $types)) {
            $type = 'bar';
        }
        
        // Get city from place details if possible
        $city = $defaultCity;
        $details = getPlaceDetails($placeId, $apiKey);
        if ($details && isset($details['address_components'])) {
            $extractedCity = extractCity($details['address_components']);
            if ($extractedCity) {
                $city = $extractedCity;
            }
        }
        
        // Get additional data
        $rating = $place['rating'] ?? null;
        $priceLevel = $place['price_level'] ?? null;
        $vicinity = $place['vicinity'] ?? '';
        
        // Extract cuisine from types
        $cuisineTypes = ['american_restaurant', 'italian_restaurant', 'chinese_restaurant', 
                        'japanese_restaurant', 'mexican_restaurant', 'indian_restaurant',
                        'thai_restaurant', 'vietnamese_restaurant', 'korean_restaurant',
                        'mediterranean_restaurant', 'french_restaurant', 'greek_restaurant',
                        'seafood_restaurant', 'steak_house', 'pizza_restaurant',
                        'burger_restaurant', 'sushi_restaurant', 'barbecue_restaurant'];
        
        $cuisine = 'Various';
        foreach ($types as $t) {
            if (in_array($t, $cuisineTypes)) {
                $cuisine = str_replace('_restaurant', '', $t);
                $cuisine = str_replace('_', ' ', $cuisine);
                $cuisine = ucwords($cuisine);
                break;
            }
        }
        
        $venues[] = [
            'id' => 'gplace:' . $placeId,
            'name' => $name,
            'lat' => floatval($lat),
            'lng' => floatval($lng),
            'type' => $type,
            'cuisine' => $cuisine,
            'city' => $city,
            'address' => $vicinity,
            'rating' => $rating,
            'price_level' => $priceLevel,
            'source' => 'google_places',
            'source_id' => $placeId
        ];
    }
    
    return $venues;
}

/**
 * Ingest restaurants for a single area
 */
function ingestArea($pdo, $name, $lat, $lng, $radius, $type, $apiKey) {
    logMessage("Processing: $name ($lat, $lng)");
    
    // Create grid cell key
    $gridSize = 0.04;
    $gridLat = floor($lat / $gridSize) * $gridSize;
    $gridLng = floor($lng / $gridSize) * $gridSize;
    $cellKey = sprintf('%.4f,%.4f', $gridLat, $gridLng);
    
    // Check if recently updated
    $stmt = $pdo->prepare('SELECT last_fetched FROM grid_cells WHERE cell_key = :cell');
    $stmt->execute([':cell' => $cellKey]);
    $row = $stmt->fetch(PDO::FETCH_ASSOC);
    if ($row && (time() - intval($row['last_fetched'])) < 604800) {
        logMessage("  Skipping - updated within last 7 days");
        return 0;
    }
    
    $allVenues = [];
    $pageToken = null;
    $pageCount = 0;
    
    // Fetch all pages (max 3 pages = 60 results per area due to Google Places limits)
    do {
        logMessage("  Fetching page " . ($pageCount + 1) . "...");
        $result = fetchGooglePlaces($lat, $lng, $radius, $type, $apiKey, $pageToken);
        
        if ($result['status'] !== 'OK' && $result['status'] !== 'ZERO_RESULTS') {
            logMessage("  API Status: " . $result['status']);
            break;
        }
        
        $places = $result['results'] ?? [];
        logMessage("  Got " . count($places) . " places");
        
        $venues = parseGooglePlaces($places, $name, $apiKey);
        $allVenues = array_merge($allVenues, $venues);
        
        $pageToken = $result['next_page_token'] ?? null;
        $pageCount++;
        
        // Wait for next page token to become valid (Google requires ~2s delay)
        if ($pageToken && $pageCount < 3) {
            logMessage("  Waiting for next page...");
            sleep(2);
        }
    } while ($pageToken && $pageCount < 3);
    
    logMessage("  Total venues from API: " . count($allVenues));
    
    if (count($allVenues) === 0) {
        return 0;
    }
    
    // Deduplicate by place_id
    $seen = [];
    $uniqueVenues = [];
    foreach ($allVenues as $v) {
        $key = $v['source_id'];
        if (!isset($seen[$key])) {
            $seen[$key] = true;
            $uniqueVenues[] = $v;
        }
    }
    
    logMessage("  Unique venues: " . count($uniqueVenues));
    
    // Insert into database
    $now = time();
    $inserted = 0;
    
    $stmt = $pdo->prepare('INSERT INTO venues 
        (id, name, lat, lng, type, cuisine, city, address, rating, price_level, source, source_id, last_updated, first_seen, grid_cell)
        VALUES (:id, :name, :lat, :lng, :type, :cuisine, :city, :address, :rating, :price_level, :source, :source_id, :updated, :first, :cell)
        ON DUPLICATE KEY UPDATE
        name = VALUES(name), lat = VALUES(lat), lng = VALUES(lng), type = VALUES(type),
        cuisine = VALUES(cuisine), city = VALUES(city), address = VALUES(address),
        rating = VALUES(rating), price_level = VALUES(price_level), 
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
                ':address' => $v['address'],
                ':rating' => $v['rating'],
                ':price_level' => $v['price_level'],
                ':source' => $v['source'],
                ':source_id' => $v['source_id'],
                ':updated' => $now,
                ':first' => $now,
                ':cell' => $cellKey
            ]);
            $inserted++;
        } catch (PDOException $e) {
            logMessage("  DB Error: " . $e->getMessage());
        }
    }
    
    // Update grid cell
    $south = $gridLat;
    $north = $gridLat + $gridSize;
    $west = $gridLng;
    $east = $gridLng + $gridSize;
    
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
logMessage("=== FLORIDA GOOGLE PLACES INGESTION STARTED ===");
logMessage("Target: " . count($floridaAreas) . " areas");
logMessage("API Key: " . ($googleApiKey === 'YOUR_API_KEY_HERE' ? 'NOT CONFIGURED' : substr($googleApiKey, 0, 10) . '...'));

if ($googleApiKey === 'YOUR_API_KEY_HERE') {
    logMessage("ERROR: Please set GOOGLE_PLACES_API_KEY environment variable or update the script!");
    logMessage("Get your free API key at: https://developers.google.com/maps/documentation/places/web-service/get-api-key");
    exit(1);
}

$pdo = initDatabase();

$totalVenues = 0;
$processed = 0;
$startTime = time();
$lastReportTime = $startTime;
$lastReportCount = 0;

foreach ($floridaAreas as $area) {
    $count = ingestArea($pdo, $area['name'], $area['lat'], $area['lng'], $radiusMeters, $type, $googleApiKey);
    $totalVenues += $count;
    $processed++;
    
    // Progress report every area
    logMessage("Progress: $processed / " . count($floridaAreas) . " areas | Total venues: $totalVenues");
    
    // Report every 50k venues (if we ever hit that)
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
    
    // Sleep between areas to avoid rate limits
    if ($processed < count($floridaAreas)) {
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
logMessage("Final DB count: {$row[0]} venues across {$row[1]} cities");
?>
