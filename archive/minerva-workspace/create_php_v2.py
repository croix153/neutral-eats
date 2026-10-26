#!/usr/bin/env python3
"""
Lake Mary Yelp Enrichment - PHP Version for Server (Fixed)
Uses proper datetime format
"""

php_script = '''<?php
// Lake Mary Yelp Enrichment Script
// Uses Yelp Fusion API to fill gaps in Lake Mary, FL

// Yelp API Key (already configured on server)
$YELP_API_KEY = 'REDACTED';

// Database config
$db_host = 'localhost';
$db_user = 'neutraleats_user';
$db_pass = 'REDACTED';
$db_name = 'neutraleats';

// Lake Mary areas to scan
$areas = [
    ["name" => "Lake Mary Center", "lat" => 28.7589, "lng" => -81.3178, "radius" => 2000],
    ["name" => "Heathrow", "lat" => 28.7750, "lng" => -81.3400, "radius" => 2500],
    ["name" => "Colonial TownPark", "lat" => 28.7450, "lng" => -81.3100, "radius" => 1500],
    ["name" => "Lake Mary Blvd", "lat" => 28.7550, "lng" => -81.3300, "radius" => 2000],
    ["name" => "Rinehart Rd", "lat" => 28.7600, "lng" => -81.3500, "radius" => 1500],
    ["name" => "Lake Mary Marketplace", "lat" => 28.7500, "lng" => -81.3200, "radius" => 1500],
    ["name" => "Timacuan", "lat" => 28.7650, "lng" => -81.3250, "radius" => 1200],
];

echo "🍽️  Neutral Eats - Lake Mary Yelp Enrichment\\n";
echo str_repeat("=", 60) . "\\n";

// Connect to database
$mysqli = new mysqli($db_host, $db_user, $db_pass, $db_name);
if ($mysqli->connect_error) {
    die("❌ Database connection failed: " . $mysqli->connect_error);
}
echo "✅ Connected to database\\n";

// Get current count before
$result = $mysqli->query("SELECT COUNT(*) as count FROM venues WHERE lat BETWEEN 28.73 AND 28.78 AND lng BETWEEN -81.36 AND -81.30");
$before_count = $result->fetch_assoc()['count'];
echo "📊 Current Lake Mary venues: {$before_count}\\n\\n";

// Function to check if venue exists
function venue_exists($mysqli, $name, $lat, $lng) {
    $stmt = $mysqli->prepare("SELECT id FROM venues WHERE LOWER(name) = LOWER(?) AND ABS(lat - ?) < 0.001 AND ABS(lng - ?) < 0.001 LIMIT 1");
    $stmt->bind_param("sdd", $name, $lat, $lng);
    $stmt->execute();
    $result = $stmt->get_result();
    return $result->num_rows > 0;
}

// Function to categorize venue type
function categorize_type($categories) {
    $cat_str = strtolower(implode(' ', array_column($categories, 'title')));
    if (strpos($cat_str, 'cafe') !== false || strpos($cat_str, 'coffee') !== false || strpos($cat_str, 'bakery') !== false) {
        return 'cafe';
    } elseif (strpos($cat_str, 'bar') !== false || strpos($cat_str, 'pub') !== false) {
        return 'bar';
    } elseif (strpos($cat_str, 'fast food') !== false) {
        return 'fast_food';
    }
    return 'restaurant';
}

// Function to fetch from Yelp
function fetch_yelp($lat, $lng, $radius, $api_key, $offset = 0) {
    $url = "https://api.yelp.com/v3/businesses/search";
    $params = http_build_query([
        'latitude' => $lat,
        'longitude' => $lng,
        'radius' => $radius,
        'categories' => 'restaurants,food,cafes,bars',
        'limit' => 50,
        'offset' => $offset,
        'sort_by' => 'best_match'
    ]);
    
    $ch = curl_init("{$url}?{$params}");
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_HTTPHEADER, ["Authorization: Bearer {$api_key}"]);
    curl_setopt($ch, CURLOPT_TIMEOUT, 30);
    
    $response = curl_exec($ch);
    $http_code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);
    
    if ($http_code !== 200) {
        echo "⚠️  Yelp API error: HTTP {$http_code}\\n";
        return [];
    }
    
    $data = json_decode($response, true);
    return $data['businesses'] ?? [];
}

// Function to insert venue
function insert_venue($mysqli, $business) {
    $coords = $business['coordinates'] ?? [];
    $location = $business['location'] ?? [];
    
    $name = $business['name'];
    $lat = $coords['latitude'] ?? 0;
    $lng = $coords['longitude'] ?? 0;
    $type = categorize_type($business['categories'] ?? []);
    $cuisine = implode(', ', array_column($business['categories'] ?? [], 'title'));
    $rating = $business['rating'] ?? null;
    $price = $business['price'] ?? '';
    $price_level = strlen($price);
    $address = implode(', ', $location['display_address'] ?? []);
    $city = $location['city'] ?? '';
    $state = $location['state'] ?? '';
    $zip = $location['zip_code'] ?? '';
    $phone = $business['phone'] ?? '';
    $website = $business['url'] ?? '';
    $source_id = $business['id'];
    $now = date('Y-m-d H:i:s');
    
    // Skip closed businesses
    if ($business['is_closed'] ?? false) {
        return ['added' => false, 'reason' => 'closed'];
    }
    
    // Check if exists
    if (venue_exists($mysqli, $name, $lat, $lng)) {
        return ['added' => false, 'reason' => 'duplicate'];
    }
    
    // Insert
    $stmt = $mysqli->prepare("INSERT INTO venues (id, name, lat, lng, type, cuisine, brand, rating, price_level, address, city, state, zip, phone, website, source, source_id, is_active, last_updated, first_seen, check_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'yelp', ?, 1, ?, ?, 1) ON DUPLICATE KEY UPDATE rating = VALUES(rating), price_level = VALUES(price_level), last_updated = VALUES(last_updated), check_count = check_count + 1");
    
    $brand = '';
    $id = $source_id;
    $stmt->bind_param("sddsssdisssssssss", $id, $name, $lat, $lng, $type, $cuisine, $brand, $rating, $price_level, $address, $city, $state, $zip, $phone, $website, $source_id, $now, $now);
    
    if ($stmt->execute()) {
        return ['added' => true, 'reason' => 'new'];
    } else {
        return ['added' => false, 'reason' => 'error: ' . $stmt->error];
    }
}

// Process each area
$total_added = 0;
$total_skipped = 0;
$api_calls = 0;

foreach ($areas as $area) {
    echo "🔍 Scanning: {$area['name']}...\\n";
    
    // Fetch up to 100 results (2 pages)
    for ($offset = 0; $offset <= 50; $offset += 50) {
        $businesses = fetch_yelp($area['lat'], $area['lng'], $area['radius'], $YELP_API_KEY, $offset);
        $api_calls++;
        
        $added = 0;
        $skipped = 0;
        
        foreach ($businesses as $business) {
            $result = insert_venue($mysqli, $business);
            if ($result['added']) {
                $added++;
                $total_added++;
            } else {
                $skipped++;
                $total_skipped++;
            }
        }
        
        echo "  Offset {$offset}: +{$added} new, {$skipped} skipped\\n";
        
        // Rate limiting
        usleep(500000); // 0.5 seconds
    }
}

echo "\\n" . str_repeat("=", 60) . "\\n";
echo "✅ Lake Mary enrichment complete!\\n";
echo "📈 Added: {$total_added} new venues\\n";
echo "🔄 Skipped: {$total_skipped}\\n";
echo "🔑 API calls: {$api_calls}\\n";

// Get final count
$result = $mysqli->query("SELECT COUNT(*) as count FROM venues WHERE lat BETWEEN 28.73 AND 28.78 AND lng BETWEEN -81.36 AND -81.30");
$after_count = $result->fetch_assoc()['count'];
echo "\\n📊 Before: {$before_count} venues\\n";
echo "📊 After: {$after_count} venues\\n";
echo "📊 Net gain: " . ($after_count - $before_count) . " venues\\n";

// Show sample of what was added
echo "\\n🍽️ Sample of venues added:\\n";
$result = $mysqli->query("SELECT name, type, cuisine, rating, address FROM venues WHERE source = 'yelp' AND lat BETWEEN 28.73 AND 28.78 AND lng BETWEEN -81.36 AND -81.30 ORDER BY first_seen DESC LIMIT 10");
while ($row = $result->fetch_assoc()) {
    $rating_str = $row['rating'] ? "⭐ {$row['rating']}" : "No rating";
    echo "  - {$row['name']} ({$row['type']}) - {$rating_str}\\n";
}

$mysqli->close();
echo "\\n🦉 All done!\\n";
?>'''

# Save PHP script
with open('/root/.openclaw/workspace/lake_mary_yelp_v2.php', 'w') as f:
    f.write(php_script)

print("✅ Created lake_mary_yelp_v2.php with datetime fix")
