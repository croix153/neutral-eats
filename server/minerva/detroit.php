<?php
// Detroit MI Yelp Enrichment

$YELP_API_KEY = 'REDACTED';

$db = new mysqli('localhost', 'neutraleats_user', 'REDACTED', 'neutraleats');
if ($db->connect_error) die("DB Error: " . $db->connect_error);

echo "🏭 Detroit MI Yelp Enrichment\n";
echo str_repeat("=", 60) . "\n";

$before = $db->query("SELECT COUNT(*) as c FROM venues WHERE lat BETWEEN 42.30 AND 42.40 AND lng BETWEEN -83.15 AND -83.00")->fetch_assoc()['c'];
echo "Detroit before: $before\n\n";

$areas = [
    ["Downtown Detroit", 42.3314, -83.0458, 3000],
    ["Midtown Detroit", 42.3539, -83.0640, 2000],
    ["Greektown", 42.3346, -83.0416, 1500],
    ["Corktown", 42.3236, -83.0819, 1500],
    ["Eastern Market", 42.3436, -83.0405, 1500],
    ["Royal Oak", 42.4895, -83.1446, 2000],
    ["Ferndale", 42.4606, -83.1346, 1500],
    ["Birmingham", 42.5467, -83.2113, 1500],
    ["Troy", 42.6064, -83.1498, 2000],
];

$total_added = 0;

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
echo "✅ Complete! Added: $total_added venues\n";

$after = $db->query("SELECT COUNT(*) as c FROM venues WHERE lat BETWEEN 42.30 AND 42.40 AND lng BETWEEN -83.15 AND -83.00")->fetch_assoc()['c'];
echo "Detroit: $before → $after (+" . ($after - $before) . ")\n";

$db->close();
echo "\n🦉 Done!\n";
