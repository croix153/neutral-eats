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
 *
 * Enrichment merge (2026-10-26): rows are LEFT JOINed with the
 * `enrichment` side table (Yelp data; see pipeline/enrich_yelp.py).
 * Enrichment values win when present — rating, reviewCount,
 * priceLevel, tableService — with the venues table's own legacy
 * fields as fallback. Venues flagged is_closed in enrichment are
 * excluded. Enrichment is display/closure data only, never a
 * ranking input: ORDER BY below is unchanged.
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
    $whereClauses = ['venues.is_active = 1'];

    // Enrichment closure suppression: hide venues Yelp says are closed
    $whereClauses[] = '(e.is_closed IS NULL OR e.is_closed = 0)';

    // Spatial filter
    $whereClauses[] = 'venues.lat >= :south AND venues.lat <= :north AND venues.lng >= :west AND venues.lng <= :east';
    $params[':south'] = $south;
    $params[':north'] = $north;
    $params[':west'] = $west;
    $params[':east'] = $east;
    
    // Type filter
    if ($type && in_array($type, ['restaurant', 'cafe', 'bar', 'pub'])) {
        $whereClauses[] = 'venues.type = :type';
        $params[':type'] = $type;
    }

    // Full-text search
    $searchJoin = '';
    if ($search) {
        $whereClauses[] = 'MATCH(venues.name, venues.cuisine, venues.brand, venues.address) AGAINST (:search IN BOOLEAN MODE)';
        $params[':search'] = $search . '*';
    }
    
    $whereSql = implode(' AND ', $whereClauses);
    
    $sql = "SELECT
        venues.id, venues.name, venues.lat, venues.lng, venues.type,
        venues.cuisine, venues.brand,
        venues.rating, venues.price_level, venues.rating_count,
        venues.address, venues.phone, venues.website,
        venues.source, venues.last_updated,
        e.rating AS e_rating, e.review_count AS e_review_count,
        e.price_level AS e_price_level,
        e.table_service AS e_table_service, e.is_closed AS e_is_closed
    FROM venues
    LEFT JOIN enrichment e ON e.venue_id = venues.id
    WHERE $whereSql
    ORDER BY
        FIELD(venues.source, 'overture', 'osm'),
        venues.rating DESC,
        venues.name ASC
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
            'rating' => $row['e_rating'] !== null ? floatval($row['e_rating']) : ($row['rating'] ? floatval($row['rating']) : null),
            'reviewCount' => $row['e_review_count'] !== null ? intval($row['e_review_count']) : (!empty($row['rating_count']) ? intval($row['rating_count']) : null),
            'priceLevel' => $row['e_price_level'] !== null ? intval($row['e_price_level']) : ($row['price_level'] ? intval($row['price_level']) : null),
            'tableService' => $row['e_table_service'] !== null ? intval($row['e_table_service']) === 1 : null,
            'isClosed' => $row['e_is_closed'] !== null ? intval($row['e_is_closed']) === 1 : null,
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