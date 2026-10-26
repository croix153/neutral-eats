<?php
set_time_limit(0);
ini_set('memory_limit', '1024M');
ini_set('display_errors', 1);
error_reporting(E_ALL);

$FLORIDA_AREAS = [
    ['name'=>'South Beach','lat'=>25.7907,'lng'=>-80.1300,'radius'=>5000],
    ['name'=>'Wynwood','lat'=>25.8033,'lng'=>-80.1992,'radius'=>4000],
    ['name'=>'Coral Gables','lat'=>25.7215,'lng'=>-80.2684,'radius'=>6000],
    ['name'=>'Brickell','lat'=>25.7590,'lng'=>-80.1930,'radius'=>4500],
    ['name'=>'Fort Lauderdale','lat'=>26.1224,'lng'=>-80.1373,'radius'=>8000],
    ['name'=>'Hollywood FL','lat'=>26.0112,'lng'=>-80.1495,'radius'=>7000],
    ['name'=>'Boca Raton','lat'=>26.3683,'lng'=>-80.1289,'radius'=>7000],
    ['name'=>'West Palm Beach','lat'=>26.7153,'lng'=>-80.0534,'radius'=>7500],
    ['name'=>'Delray Beach','lat'=>26.4615,'lng'=>-80.0728,'radius'=>6000],
    ['name'=>'Pompano Beach','lat'=>26.2379,'lng'=>-80.1248,'radius'=>6000],
    ['name'=>'Coconut Grove','lat'=>25.7256,'lng'=>-80.2427,'radius'=>5000],
    ['name'=>'Design District','lat'=>25.8134,'lng'=>-80.1945,'radius'=>4000],
    ['name'=>'Aventura','lat'=>25.9565,'lng'=>-80.1392,'radius'=>5500],
    ['name'=>'Boynton Beach','lat'=>26.5253,'lng'=>-80.0664,'radius'=>6000],
    ['name'=>'Jupiter','lat'=>26.9342,'lng'=>-80.0942,'radius'=>6000],
    ['name'=>'Palm Beach','lat'=>26.7056,'lng'=>-80.0364,'radius'=>5000],
    ['name'=>'Jacksonville Downtown','lat'=>30.3322,'lng'=>-81.6557,'radius'=>8000],
    ['name'=>'Riverside Jacksonville','lat'=>30.3166,'lng'=>-81.6944,'radius'=>5500],
    ['name'=>'San Marco','lat'=>30.3039,'lng'=>-81.6551,'radius'=>5000],
    ['name'=>'Atlantic Beach','lat'=>30.3344,'lng'=>-81.3987,'radius'=>5000],
    ['name'=>'Jacksonville Beach','lat'=>30.2841,'lng'=>-81.3961,'radius'=>5500],
    ['name'=>'Ponte Vedra','lat'=>30.2400,'lng'=>-81.3853,'radius'=>6000],
    ['name'=>'Orange Park','lat'=>30.1661,'lng'=>-81.7065,'radius'=>5500],
    ['name'=>'St Johns Town Center','lat'=>30.2508,'lng'=>-81.5299,'radius'=>5000],
    ['name'=>'Tallahassee','lat'=>30.4383,'lng'=>-84.2807,'radius'=>8000],
    ['name'=>'Gainesville','lat'=>29.6516,'lng'=>-82.3248,'radius'=>8000],
    ['name'=>'Lakeland','lat'=>28.0395,'lng'=>-81.9498,'radius'=>7500],
    ['name'=>'Daytona Beach','lat'=>29.2108,'lng'=>-81.0228,'radius'=>7500],
    ['name'=>'Pensacola','lat'=>30.4213,'lng'=>-87.2169,'radius'=>8000],
    ['name'=>'Fort Myers','lat'=>26.6406,'lng'=>-81.8723,'radius'=>7500],
    ['name'=>'Naples','lat'=>26.1420,'lng'=>-81.7948,'radius'=>7500],
    ['name'=>'Melbourne','lat'=>28.0836,'lng'=>-80.6081,'radius'=>7000],
    ['name'=>'Port St Lucie','lat'=>27.2730,'lng'=>-80.3582,'radius'=>7000],
    ['name'=>'Ocala','lat'=>29.1872,'lng'=>-82.1401,'radius'=>7000],
    ['name'=>'Panama City','lat'=>30.1588,'lng'=>-85.6602,'radius'=>7000],
    ['name'=>'Destin','lat'=>30.3935,'lng'=>-86.4958,'radius'=>6000],
    ['name'=>'Vero Beach','lat'=>27.6386,'lng'=>-80.3973,'radius'=>6000],
    ['name'=>'The Villages','lat'=>28.9270,'lng'=>-81.9906,'radius'=>7000],
    ['name'=>'St Augustine','lat'=>29.9012,'lng'=>-81.3124,'radius'=>6500],
    ['name'=>'Port Charlotte','lat'=>26.9762,'lng'=>-82.0906,'radius'=>6000],
    ['name'=>'Bonita Springs','lat'=>26.3398,'lng'=>-81.7787,'radius'=>5500],
];

function log_msg($msg) {
    $line = date('Y-m-d H:i:s') . " | " . $msg . "\n";
    file_put_contents('/var/www/html/minerva/data/florida_ingest.log', $line, FILE_APPEND);
    echo $line;
}

function get_db() {
    $db = new SQLite3('/var/www/html/minerva/data/neutraleats.db');
    $db->exec('PRAGMA journal_mode = WAL');
    $db->exec('PRAGMA synchronous = NORMAL');
    return $db;
}

function fetch_overpass($lat, $lng, $radius) {
    $amenities = ['restaurant', 'cafe', 'fast_food', 'bar', 'pub', 'ice_cream', 'biergarten', 'food_court'];
    $shops = ['bakery', 'confectionery', 'wine', 'deli'];
    
    $parts = [];
    foreach ($amenities as $a) {
        $parts[] = 'node["amenity"="' . $a . '"](around:' . $radius . ',' . $lat . ',' . $lng . ')';
        $parts[] = 'way["amenity"="' . $a . '"](around:' . $radius . ',' . $lat . ',' . $lng . ')';
    }
    foreach ($shops as $s) {
        $parts[] = 'node["shop"="' . $s . '"](around:' . $radius . ',' . $lat . ',' . $lng . ')';
        $parts[] = 'way["shop"="' . $s . '"](around:' . $radius . ',' . $lat . ',' . $lng . ')';
    }
    
    $query = '[out:json][timeout:60];(' . implode(';', $parts) . ';);out body center;';
    
    $url = 'https://overpass-api.de/api/interpreter';
    
    $ch = curl_init($url);
    curl_setopt($ch, CURLOPT_POST, true);
    curl_setopt($ch, CURLOPT_POSTFIELDS, http_build_query(['data'=>$query]));
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_TIMEOUT, 65);
    curl_setopt($ch, CURLOPT_CONNECTTIMEOUT, 15);
    curl_setopt($ch, CURLOPT_HTTPHEADER, ['User-Agent: NeutralEats/1.0']);
    
    $resp = curl_exec($ch);
    $err = curl_error($ch);
    $code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);
    
    if ($resp === false) {
        log_msg("  Curl error: $err");
        return null;
    }
    if ($code != 200) {
        log_msg("  HTTP $code");
        return null;
    }
    
    $data = json_decode($resp, true);
    if (!$data) {
        log_msg("  JSON decode failed");
        return null;
    }
    return $data;
}

function parse_venue($e) {
    if (!isset($e['tags'])) return null;
    $t = $e['tags'];
    $type = $t['amenity'] ?? $t['shop'] ?? 'restaurant';
    if (isset($e['lat']) && isset($e['lon'])) { $lat=$e['lat']; $lng=$e['lon']; }
    elseif (isset($e['center'])) { $lat=$e['center']['lat']; $lng=$e['center']['lon']; }
    else return null;
    if ($lat < 24 || $lat > 31 || $lng < -88 || $lng > -79) return null;
    $name = $t['name'] ?? 'Unknown';
    $id = hash('sha256', $name . $lat . $lng);
    return ['id'=>$id,'name'=>$name,'lat'=>$lat,'lng'=>$lng,'type'=>$type,'cuisine'=>($t['cuisine']??null),'brand'=>($t['brand']??null),'source'=>'osm','source_id'=>(string)($e['id']??''),'grid'=>get_grid($lat,$lng)];
}

function get_grid($lat,$lng) {
    return sprintf("%.2f,%.2f", floor($lat*20)/20, floor($lng*20)/20);
}

function save_venues($db, $venues) {
    $stmt = $db->prepare("INSERT OR IGNORE INTO venues (id,name,lat,lng,type,cuisine,brand,source,source_id,last_updated,first_seen,grid_cell,check_count) VALUES (:id,:name,:lat,:lng,:type,:cuisine,:brand,:source,:sid,:upd,:seen,:grid,1)");
    $now = time(); $ins=0;
    foreach ($venues as $v) {
        $stmt->bindValue(':id',$v['id']); $stmt->bindValue(':name',$v['name']); $stmt->bindValue(':lat',$v['lat']); $stmt->bindValue(':lng',$v['lng']);
        $stmt->bindValue(':type',$v['type']); $stmt->bindValue(':cuisine',$v['cuisine']); $stmt->bindValue(':brand',$v['brand']);
        $stmt->bindValue(':source',$v['source']); $stmt->bindValue(':sid',$v['source_id']); $stmt->bindValue(':upd',$now); $stmt->bindValue(':seen',$now); $stmt->bindValue(':grid',$v['grid']);
        if ($stmt->execute()) $ins++;
    }
    return $ins;
}

function update_grid($db, $cell, $lat, $lng, $count) {
    $stmt = $db->prepare("INSERT OR REPLACE INTO grid_cells (cell_key,lat_min,lat_max,lng_min,lng_max,venue_count,last_fetched,fetch_count) VALUES (:key,:lat1,:lat2,:lng1,:lng2,:cnt,:time,COALESCE((SELECT fetch_count FROM grid_cells WHERE cell_key=:key2),0)+1)");
    $g1=floor($lat*20)/20; $g2=floor($lng*20)/20;
    $stmt->bindValue(':key',$cell); $stmt->bindValue(':lat1',$g1); $stmt->bindValue(':lat2',$g1+0.05);
    $stmt->bindValue(':lng1',$g2); $stmt->bindValue(':lng2',$g2+0.05); $stmt->bindValue(':cnt',$count); $stmt->bindValue(':time',time()); $stmt->bindValue(':key2',$cell);
    $stmt->execute();
}

log_msg("========================================");
log_msg("FLORIDA INGESTION - CONTINUING AREAS 40-80");
log_msg("========================================");
$db = get_db();
$start = $db->querySingle("SELECT COUNT(*) FROM venues");
log_msg("Starting with $start venues");
$total_new = 0;
foreach ($FLORIDA_AREAS as $i=>$a) {
    $area_num = $i + 40;
    log_msg("[$area_num/80] {$a['name']}...");
    $data = fetch_overpass($a['lat'], $a['lng'], $a['radius']);
    if (!$data || !isset($data['elements'])) { log_msg("  ✗ Failed"); continue; }
    $venues = [];
    foreach ($data['elements'] as $e) { $v = parse_venue($e); if ($v) $venues[$v['id']] = $v; }
    $ins = save_venues($db, $venues);
    $grid = get_grid($a['lat'], $a['lng']);
    update_grid($db, $grid, $a['lat'], $a['lng'], count($venues));
    $total_new += $ins;
    log_msg("  ✓ Added $ins new (found " . count($venues) . ")");
    if ($area_num % 10 == 0) {
        $cur = $db->querySingle("SELECT COUNT(*) FROM venues");
        log_msg("--- PROGRESS: $cur total venues ---");
    }
    usleep(500000);
}
$final = $db->querySingle("SELECT COUNT(*) FROM venues");
$grids = $db->querySingle("SELECT COUNT(*) FROM grid_cells");
log_msg("========================================");
log_msg("DONE! Final: $final venues ($total_new new, $grids grid cells)");
log_msg("========================================");
