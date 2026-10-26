<?php
/**
 * Neutral Eats API - Venue Query Endpoint (MySQL Version)
 * Returns restaurants/venues within bounding box
 * 
 * Query params:
 *   south, west, north, east - Bounding box coordinates
 *   type - Filter by venue type (optional)
 *   limit - Max results (default 100, max 500)
 *   search - Full-text search query (optional)
 */

header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');
header('Cache-Control: public, max-age=3600'); // 1h client cache; data refreshes monthly (perf 2026-10-25)

// Database configuration
$dbHost = 'localhost';
$dbName = 'neutraleats';
$dbUser = 'neutraleats_user';
$dbPass = 'neutraleats_pass';

// Get parameters
$south = isset($_GET['south']) ? floatval($_GET['south']) : null;
$west = isset($_GET['west']) ? floatval($_GET['west']) : null;
$north = isset($_GET['north']) ? floatval($_GET['north']) : null;
$east = isset($_GET['east']) ? floatval($_GET['east']) : null;
$type = isset($_GET['type']) ? $_GET['type'] : null;
$search = isset($_GET['search']) ? $_GET['search'] : null;
$limit = min(intval($_GET['limit'] ?? 100), 500);

// Validate required params
if ($south === null || $west === null || $north === null || $east === null) {
    http_response_code(400);
    echo json_encode(['error' => 'Missing bounding box parameters (south, west, north, east)']);
    exit;
}

// Validate bounds
if ($south >= $north || $west >= $east) {
    http_response_code(400);
    echo json_encode(['error' => 'Invalid bounding box']);
    exit;
}

try {
    $pdo = new PDO("mysql:host=$dbHost;dbname=$dbName;charset=utf8mb4", $dbUser, $dbPass);
    $pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
    
    // Build query
    $params = [];
    $whereClauses = ['is_active = 1'];
    
    // Spatial filter
    $whereClauses[] = 'lat >= :south AND lat <= :north AND lng >= :west AND lng <= :east';
    $params[':south'] = $south;
    $params[':north'] = $north;
    $params[':west'] = $west;
    $params[':east'] = $east;
    
    // Type filter
    if ($type && in_array($type, ['restaurant', 'cafe', 'bar', 'pub'])) {
        $whereClauses[] = 'type = :type';
        $params[':type'] = $type;
    }
    
    // Full-text search
    $searchJoin = '';
    if ($search) {
        $whereClauses[] = 'MATCH(name, cuisine, brand, address) AGAINST (:search IN BOOLEAN MODE)';
        $params[':search'] = $search . '*';
    }
    
    $whereSql = implode(' AND ', $whereClauses);
    
    $sql = "SELECT 
        id, name, lat, lng, type, cuisine, brand, 
        rating, price_level, address, phone, website,
        source, last_updated
    FROM venues
    WHERE $whereSql
    ORDER BY 
        FIELD(source, 'overture', 'osm'),
        rating DESC,
        name ASC
    LIMIT :limit";
    
    $stmt = $pdo->prepare($sql);
    foreach ($params as $key => $val) {
        $stmt->bindValue($key, $val);
    }
    $stmt->bindValue(':limit', $limit, PDO::PARAM_INT);
    $stmt->execute();
    
    $venues = [];
    while ($row = $stmt->fetch(PDO::FETCH_ASSOC)) {
        $venues[] = [
            'id' => $row['id'],
            'name' => $row['name'],
            'lat' => floatval($row['lat']),
            'lng' => floatval($row['lng']),
            'type' => $row['type'],
            'cuisine' => $row['cuisine'] ?? 'Various',
            'brand' => $row['brand'] ?? '',
            'rating' => $row['rating'] ? floatval($row['rating']) : null,
            'priceLevel' => $row['price_level'] ? intval($row['price_level']) : null,
            'address' => $row['address'],
            'phone' => $row['phone'],
            'website' => $row['website'],
            'source' => $row['source'],
            'lastUpdated' => intval($row['last_updated'])
        ];
    }
    
    $response = [
        'success' => true,
        'venues' => $venues,
        'count' => count($venues),
        'bounds' => ['south' => $south, 'west' => $west, 'north' => $north, 'east' => $east],
        'timestamp' => time()
    ];

    $json = json_encode($response, JSON_PRETTY_PRINT);

    // ETag / conditional requests (perf 2026-10-25)
    $etag = '"' . md5($json) . '"';
    header('ETag: ' . $etag);
    if (isset($_SERVER['HTTP_IF_NONE_MATCH'])) {
        foreach (explode(',', $_SERVER['HTTP_IF_NONE_MATCH']) as $candidate) {
            $candidate = trim($candidate, 'W/ ');
            // mod_deflate appends -gzip to the ETag of compressed responses
            if (substr($candidate, -6) === '-gzip"') {
                $candidate = substr($candidate, 0, -6) . '"';
            }
            if ($candidate === '*' || $candidate === $etag) {
                http_response_code(304);
                exit;
            }
        }
    }

    echo $json;
    
} catch (Exception $e) {
    http_response_code(500);
    echo json_encode(['error' => 'Database error: ' . $e->getMessage()]);
}
?>