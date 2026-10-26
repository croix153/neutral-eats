<?php
// Winter Springs & Longwood Yelp Enrichment

$YELP_API_KEY = 'REDACTED';

$db = new mysqli('localhost', 'neutraleats_user', 'REDACTED', 'neutraleats');
if ($db->connect_error) die("DB Error: " . $db->connect_error);

echo "🍽️ Winter Springs & Longwood Yelp Enrichment\n";
echo str_repeat("=", 60) . "\n";

$before_ws = $db->query("SELECT COUNT(*) as c FROM venues WHERE lat BETWEEN 28.68 AND 28.73 AND lng BETWEEN -81.32 AND -81.25")->fetch_assoc()['c'];
$before_lw = $db->query("SELECT COUNT(*) as c FROM venues WHERE lat BETWEEN 28.68 AND 28.73 AND lng BETWEEN -81.38 AND -81.30")->fetch_assoc()['c'];
echo "Winter Springs before: $before_ws\n";
echo "Longwood before: $before_lw\n\n";

$areas = [
    ["Winter Springs Center", 28.7050, -81.2800, 2500],
    ["Winter Springs Tuscawilla", 28.7150, -81.2950, 2000],
    ["Winter Springs East", 28.7000, -81.2650, 2000],
    ["Longwood Center", 28.7000, -81.3450, 2500],
    ["Longwood South", 28.6900, -81.3300, 2000],
    ["Longwood North", 28.7150, -81.3550, 2000],
    ["Longwood SR 434", 28.7050, -81.3200, 2000],
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

$after_ws = $db->query("SELECT COUNT(*) as c FROM venues WHERE lat BETWEEN 28.68 AND 28.73 AND lng BETWEEN -81.32 AND -81.25")->fetch_assoc()['c'];
$after_lw = $db->query("SELECT COUNT(*) as c FROM venues WHERE lat BETWEEN 28.68 AND 28.73 AND lng BETWEEN -81.38 AND -81.30")->fetch_assoc()['c'];
echo "\nWinter Springs: $before_ws → $after_ws (+" . ($after_ws - $before_ws) . ")\n";
echo "Longwood: $before_lw → $after_lw (+" . ($after_lw - $before_lw) . ")\n";

$db->close();
echo "\n🦉 Done!\n";
