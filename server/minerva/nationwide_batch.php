<?php
// Batch Nationwide Enrichment

$YELP_API_KEY = 'REDACTED';

$db = new mysqli('localhost', 'neutraleats_user', 'REDACTED', 'neutraleats');
if ($db->connect_error) die("DB Error: " . $db->connect_error);

$cities = [
    ["New York City", 40.7128, -74.0060, 5000],
    ["Brooklyn", 40.6782, -73.9442, 4000],
    ["Queens", 40.7282, -73.7949, 4000],
    ["Los Angeles", 34.0522, -118.2437, 5000],
    ["Chicago", 41.8781, -87.6298, 5000],
    ["Houston", 29.7604, -95.3698, 5000],
    ["Phoenix", 33.4484, -112.0740, 5000],
    ["Philadelphia", 39.9526, -75.1652, 4000],
    ["San Antonio", 29.4241, -98.4936, 4000],
    ["San Diego", 32.7157, -117.1611, 4000],
    ["Dallas", 32.7767, -96.7970, 4000],
    ["San Jose", 37.3382, -121.8863, 4000],
    ["Austin", 30.2672, -97.7431, 4000],
    ["Fort Worth", 32.7555, -97.3308, 4000],
    ["Columbus OH", 39.9612, -82.9988, 4000],
    ["Charlotte", 35.2271, -80.8431, 4000],
    ["Indianapolis", 39.7684, -86.1581, 4000],
    ["Seattle", 47.6062, -122.3321, 4000],
    ["Denver", 39.7392, -104.9903, 4000],
    ["Washington DC", 38.9072, -77.0369, 4000],
    ["Boston", 42.3601, -71.0589, 4000],
    ["Nashville", 36.1627, -86.7816, 4000],
    ["Portland", 45.5152, -122.6784, 4000],
    ["Oklahoma City", 35.4676, -97.5164, 4000],
];

$total_added = 0;

echo "🌎 Batch Nationwide Enrichment
";
echo str_repeat("=", 70) . "\n\n";

function fetch_yelp($lat, $lng, $radius, $api_key, $offset = 0) {
    $url = "https://api.yelp.com/v3/businesses/search?" . http_build_query([
        'latitude' => $lat, 'longitude' => $lng, 'radius' => $radius,
        'categories' => 'restaurants,food,cafes,bars', 'limit' => 50,
        'offset' => $offset, 'sort_by' => 'best_match'
    ]);
    $ch = curl_init($url);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_HTTPHEADER, ["Authorization: Bearer $api_key"]);
    curl_setopt($ch, CURLOPT_TIMEOUT, 30);
    $response = curl_exec($ch);
    curl_close($ch);
    return json_decode($response, true)['businesses'] ?? [];
}

function exists($db, $name, $lat, $lng) {
    $stmt = $db->prepare("SELECT 1 FROM venues WHERE LOWER(name)=LOWER(?) AND ABS(lat-?)<0.001 AND ABS(lng-?)<0.001 LIMIT 1");
    $stmt->bind_param("sdd", $name, $lat, $lng);
    $stmt->execute();
    return $stmt->get_result()->num_rows > 0;
}

function get_type($cats) {
    $s = strtolower(json_encode($cats));
    if (strpos($s, 'cafe') !== false || strpos($s, 'coffee') !== false) return 'cafe';
    if (strpos($s, 'bar') !== false || strpos($s, 'pub') !== false) return 'bar';
    return 'restaurant';
}

foreach ($cities as $city) {
    echo "🔍 {$city[0]}...\n";
    $city_added = 0;
    
    for ($offset = 0; $offset <= 50; $offset += 50) {
        $biz = fetch_yelp($city[1], $city[2], $city[3], $YELP_API_KEY, $offset);
        $added = $skipped = 0;
        
        foreach ($biz as $b) {
            if ($b['is_closed'] ?? false) { $skipped++; continue; }
            
            $coords = $b['coordinates'] ?? [];
            $loc = $b['location'] ?? [];
            $name = $b['name'] ?? '';
            $lat = $coords['latitude'] ?? null;
            $lng = $coords['longitude'] ?? null;
            
            // Skip if missing critical data
            if (!$name || !$lat || !$lng) { $skipped++; continue; }
            
            if (exists($db, $name, $lat, $lng)) { $skipped++; continue; }
            
            $id = $b['id'];
            $type = get_type($b['categories']);
            $cuisine = implode(', ', array_column($b['categories'], 'title'));
            $brand = '';
            $rating = $b['rating'] ?? null;
            $price_lvl = strlen($b['price'] ?? '');
            $addr = implode(', ', $loc['display_address'] ?? []);
            $city_name = $loc['city'] ?? '';
            $state = $loc['state'] ?? '';
            $zip = $loc['zip_code'] ?? '';
            $phone = $b['phone'] ?? '';
            $website = $b['url'] ?? '';
            $source = 'yelp';
            $source_id = $b['id'];
            $now = time();
            
            $sql = "INSERT INTO venues (id,name,lat,lng,type,cuisine,brand,rating,price_level,address,city,state,zip,phone,website,source,source_id,first_seen) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)";
            $stmt = $db->prepare($sql);
            $stmt->bind_param("sssddssdissssssssi", $id, $name, $lat, $lng, $type, $cuisine, $brand, $rating, $price_lvl, $addr, $city_name, $state, $zip, $phone, $website, $source, $source_id, $now);
            
            if ($stmt->execute()) { $added++; $city_added++; $total_added++; }
            else { $skipped++; }
        }
        
        if ($added > 0 || $skipped > 0) {
            echo "  Offset $offset: +$added new, $skipped skipped\n";
        }
        usleep(300000); // 0.3s between calls
    }
    
    echo "  ✓ {$city[0]}: +$city_added venues\n\n";
}

echo str_repeat("=", 70) . "\n";
echo "✅ Batch Complete! Added: $total_added venues\n";

$db->close();
echo "🦉 Done!\n";
