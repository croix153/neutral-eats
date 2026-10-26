<?php
// Import Lake Mary Yelp data into database

$YELP_API_KEY = 'REDACTED';

$db = new mysqli('localhost', 'neutraleats_user', 'REDACTED', 'neutraleats');
if ($db->connect_error) die("DB Error: " . $db->connect_error);

echo "🚀 Importing Lake Mary Yelp Data\n";
echo str_repeat("=", 60) . "\n";

// Load the JSON data
$json_data = file_get_contents('lake_mary_missing.json');
$venues = json_decode($json_data, true);

echo "Found " . count($venues) . " venues to import\n\n";

$total_added = 0;
$total_skipped = 0;

function exists($db, $name, $lat, $lng) {
    $stmt = $db->prepare("SELECT 1 FROM venues WHERE LOWER(name)=LOWER(?) AND ABS(lat-?)<0.001 AND ABS(lng-?)<0.001 LIMIT 1");
    $stmt->bind_param("sdd", $name, $lat, $lng);
    $stmt->execute();
    return $stmt->get_result()->num_rows > 0;
}

function get_type($categories) {
    $cat_str = strtolower($categories);
    if (strpos($cat_str, 'cafe') !== false || strpos($cat_str, 'coffee') !== false || strpos($cat_str, 'tea') !== false) {
        return 'cafe';
    } elseif (strpos($cat_str, 'bar') !== false || strpos($cat_str, 'pub') !== false || strpos($cat_str, 'brew') !== false) {
        return 'bar';
    } elseif (strpos($cat_str, 'fast') !== false) {
        return 'fast_food';
    }
    return 'restaurant';
}

foreach ($venues as $i => $v) {
    // Skip if missing critical data
    if (empty($v['name']) || empty($v['lat']) || empty($v['lng'])) {
        $total_skipped++;
        continue;
    }
    
    // Check if exists
    if (exists($db, $v['name'], $v['lat'], $v['lng'])) {
        $total_skipped++;
        continue;
    }
    
    $id = $v['yelp_id'] ?? ('yelp_' . md5($v['name'] . $v['lat'] . $v['lng']));
    $type = get_type($v['cuisine']);
    $price_level = strlen($v['price'] ?? '');
    $now = date('Y-m-d H:i:s');
    
    $sql = "INSERT INTO venues (id, name, lat, lng, type, cuisine, brand, rating, price_level, 
            address, city, state, zip, phone, website, source, source_id, is_active, last_updated, first_seen, check_count) 
            VALUES (?, ?, ?, ?, ?, ?, '', ?, ?, ?, ?, ?, ?, ?, ?, 'yelp', ?, 1, ?, ?, 1)";
    
    $stmt = $db->prepare($sql);
    $stmt->bind_param("sddsssdissssssssi", 
        $id, $v['name'], $v['lat'], $v['lng'], $type, $v['cuisine'], 
        $v['rating'], $price_level, $v['address'], $v['city'], $v['state'], 
        $v['zip'], $v['phone'], $v['url'], $v['yelp_id'], $now, $now
    );
    
    if ($stmt->execute()) {
        $total_added++;
    } else {
        $total_skipped++;
    }
    
    // Progress update every 50
    if (($i + 1) % 50 == 0) {
        echo "  Progress: " . ($i + 1) . "/" . count($venues) . " (Added: $total_added, Skipped: $total_skipped)\n";
    }
    
    // Rate limiting
    usleep(10000); // 0.01s
}

echo "\n" . str_repeat("=", 60) . "\n";
echo "✅ Import Complete!\n";
echo "📈 Added: $total_added venues\n";
echo "🔄 Skipped: $total_skipped venues\n";

// Check final count
$result = $db->query("SELECT COUNT(*) FROM venues WHERE address LIKE '%Lake Mary%' OR city = 'Lake Mary'");
$final_count = $result->fetch_row()[0];
echo "\n📊 Total Lake Mary venues in database: $final_count\n";

$db->close();
echo "\n🦉 Done!\n";
