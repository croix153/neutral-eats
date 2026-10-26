<?php
// Longwood/Altamonte/Wekiwa Springs Plaza Check & Enrichment

$YELP_API_KEY = 'REDACTED';

$db = new mysqli('localhost', 'neutraleats_user', 'REDACTED', 'neutraleats');
if ($db->connect_error) die("DB Error: " . $db->connect_error);

echo "🔍 Springs Plaza / Longwood / Altamonte Check\n";
echo str_repeat("=", 60) . "\n";

// Check for Back Porch specifically
echo "Searching for 'Back Porch' in database...\n";
$result = $db->query("SELECT name, address, lat, lng, source FROM venues WHERE name LIKE '%back porch%' OR name LIKE '%backporch%'");
if ($result->num_rows > 0) {
    while ($row = $result->fetch_assoc()) {
        echo "  Found: {$row['name']} at {$row['address']} (source: {$row['source']})\n";
    }
} else {
    echo "  ❌ Back Porch not found in database\n";
}

// Check Springs Plaza area (approximate coordinates)
echo "\n📍 Checking Springs Plaza area (Wekiva Springs area)...\n";
$result = $db->query("SELECT name, address, source FROM venues WHERE lat BETWEEN 28.785 AND 28.795 AND lng BETWEEN -81.445 AND -81.435 ORDER BY name");
echo "Found " . $result->num_rows . " venues in Springs Plaza area:\n";
while ($row = $result->fetch_assoc()) {
    echo "  - {$row['name']} ({$row['source']})\n";
}

// Broader Longwood/Altamonte check
echo "\n📊 Current coverage:\n";
$result = $db->query("SELECT COUNT(*) as c FROM venues WHERE lat BETWEEN 28.78 AND 28.82 AND lng BETWEEN -81.48 AND -81.40");
echo "  Longwood/Altamonte/Wekiwa area: " . $result->fetch_assoc()['c'] . " venues\n";

// Now do targeted enrichment for this area
echo "\n🚀 Running targeted enrichment...\n";
$areas = [
    ["Springs Plaza", 28.7900, -81.4400, 1000],
    ["Wekiva Springs Center", 28.7920, -81.4375, 1500],
    ["Longwood SR 434", 28.7050, -81.3200, 2000],
    ["Altamonte Mall Area", 28.6650, -81.3850, 2500],
    ["Cranes Roost", 28.6680, -81.3900, 1500],
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
            
            // Highlight Back Porch if found
            if (stripos($name, 'back porch') !== false) {
                echo "  🎯 FOUND BACK PORCH: {$name} at {$addr}\n";
            }
            
            $sql = "INSERT INTO venues (id,name,lat,lng,type,cuisine,brand,rating,price_level,address,city,state,zip,phone,website,source,source_id,first_seen) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)";
            $stmt = $db->prepare($sql);
            $stmt->bind_param("sssddssdissssssssi", $id, $name, $lat, $lng, $type, $cuisine, $brand, $rating, $price_lvl, $addr, $city, $state, $zip, $phone, $website, $source, $source_id, $now);
            
            if ($stmt->execute()) { 
                $added++; 
                $total_added++;
                if (stripos($name, 'back porch') !== false) {
                    echo "  ✅ Added Back Porch!\n";
                }
            }
            else { $skipped++; }
        }
        
        echo "  Offset $offset: +$added new, $skipped skipped\n";
        usleep(500000);
    }
}

echo "\n" . str_repeat("=", 60) . "\n";
echo "✅ Complete! Added: $total_added venues\n";

// Check again for Back Porch
echo "\n🔍 Checking again for Back Porch...\n";
$result = $db->query("SELECT name, address, source FROM venues WHERE name LIKE '%back porch%' OR name LIKE '%backporch%'");
if ($result->num_rows > 0) {
    while ($row = $result->fetch_assoc()) {
        echo "  ✅ Found: {$row['name']} at {$row['address']} (source: {$row['source']})\n";
    }
} else {
    echo "  ⚠️ Back Porch still not found (may not be on Yelp)\n";
}

$db->close();
echo "\n🦉 Done!\n";
