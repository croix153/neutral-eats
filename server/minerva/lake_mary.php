<?php
// Lake Mary Yelp Enrichment - Clean Working Version

$YELP_API_KEY = 'REDACTED';

$db = new mysqli('localhost', 'neutraleats_user', 'REDACTED', 'neutraleats');
if ($db->connect_error) die("DB Error: " . $db->connect_error);

echo "🍽️ Lake Mary Yelp Enrichment\n";
echo str_repeat("=", 60) . "\n";

$before = $db->query("SELECT COUNT(*) as c FROM venues WHERE lat BETWEEN 28.73 AND 28.78 AND lng BETWEEN -81.36 AND -81.30")->fetch_assoc()['c'];
echo "Current venues: $before\n\n";

$areas = [
    ["Lake Mary Center", 28.7589, -81.3178, 2000],
    ["Heathrow", 28.7750, -81.3400, 2500],
    ["Colonial TownPark", 28.7450, -81.3100, 1500],
    ["Lake Mary Blvd", 28.7550, -81.3300, 2000],
    ["Rinehart Rd", 28.7600, -81.3500, 1500],
    ["Lake Mary Marketplace", 28.7500, -81.3200, 1500],
    ["Timacuan", 28.7650, -81.3250, 1200],
];

$total_added = 0;
$total_skipped = 0;

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

foreach ($areas as $area) {
    echo "🔍 {$area[0]}...\n";
    
    for ($offset = 0; $offset <= 50; $offset += 50) {
        $biz = fetch_yelp($area[1], $area[2], $area[3], $YELP_API_KEY, $offset);
        $added = $skipped = 0;
        
        foreach ($biz as $b) {
            if ($b['is_closed'] ?? false) { $skipped++; continue; }
            
            $coords = $b['coordinates'];
            $loc = $b['location'];
            $name = $b['name'];
            $lat = $coords['latitude'];
            $lng = $coords['longitude'];
            
            if (exists($db, $name, $lat, $lng)) { $skipped++; continue; }
            
            // Prepare all values
            $id = $b['id'];
            $type = get_type($b['categories']);
            $cuisine = implode(', ', array_column($b['categories'], 'title'));
            $brand = '';
            $rating = $b['rating'] ?? null;
            $price_lvl = strlen($b['price'] ?? '');
            $addr = implode(', ', $loc['display_address'] ?? []);
            $city = $loc['city'] ?? '';
            $state = $loc['state'] ?? '';
            $zip = $loc['zip_code'] ?? '';
            $phone = $b['phone'] ?? '';
            $website = $b['url'] ?? '';
            $source = 'yelp';
            $source_id = $b['id'];
            $now = time();
            
            // 18 fields: id, name, lat, lng, type, cuisine, brand, rating, price_level, address, city, state, zip, phone, website, source, source_id, first_seen
            // Types: s(id) s(name) d(lat) d(lng) s(type) s(cuisine) s(brand) d(rating) i(price_level) s(address) s(city) s(state) s(zip) s(phone) s(website) s(source) s(source_id) i(first_seen)
            $sql = "INSERT INTO venues (id,name,lat,lng,type,cuisine,brand,rating,price_level,address,city,state,zip,phone,website,source,source_id,first_seen) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)";
            $stmt = $db->prepare($sql);
            $stmt->bind_param("sssddssdissssssssi", $id, $name, $lat, $lng, $type, $cuisine, $brand, $rating, $price_lvl, $addr, $city, $state, $zip, $phone, $website, $source, $source_id, $now);
            
            if ($stmt->execute()) { $added++; $total_added++; }
            else { $skipped++; }
        }
        
        echo "  Offset $offset: +$added new, $skipped skipped\n";
        usleep(500000);
    }
}

echo "\n" . str_repeat("=", 60) . "\n";
echo "✅ Complete! Added: $total_added, Skipped: $total_skipped\n";

$after = $db->query("SELECT COUNT(*) as c FROM venues WHERE lat BETWEEN 28.73 AND 28.78 AND lng BETWEEN -81.36 AND -81.30")->fetch_assoc()['c'];
echo "Before: $before, After: $after, Net gain: " . ($after - $before) . "\n";

echo "\n🍽️ Sample venues:\n";
$res = $db->query("SELECT name, type, rating FROM venues WHERE source='yelp' AND lat BETWEEN 28.73 AND 28.78 LIMIT 10");
while ($r = $res->fetch_assoc()) {
    $stars = $r['rating'] ? "⭐{$r['rating']}" : "no rating";
    echo "  - {$r['name']} ({$r['type']}) $stars\n";
}

$db->close();
echo "\n🦉 Done!\n";
