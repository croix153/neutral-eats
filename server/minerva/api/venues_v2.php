<?php
/**
 * Neutral Eats API - Venue Query Endpoint v2.0
 * Enhanced for multi-source government and commercial data
 * 
 * Query params:
 *   south, west, north, east - Bounding box coordinates (required)
 *   type - Filter by venue type (optional)
 *   search - Full-text search query (optional)
 *   min_confidence - Minimum confidence score 0-1 (default 0.30)
 *   include_closed - Include closed venues (default false)
 *   source - Filter by data source (optional)
 *   limit - Max results (default 100, max 500)
 *   offset - Pagination offset
 */

header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');
header('Cache-Control: public, max-age=300');

require_once __DIR__ . '/../config/database.php';

try {
    $pdo = getDatabaseConnection();
    
    // Parse parameters
    $south = isset($_GET['south']) ? floatval($_GET['south']) : null;
    $west = isset($_GET['west']) ? floatval($_GET['west']) : null;
    $north = isset($_GET['north']) ? floatval($_GET['north']) : null;
    $east = isset($_GET['east']) ? floatval($_GET['east']) : null;
    
    // Validate bounding box
    if ($south === null || $west === null || $north === null || $east === null) {
        http_response_code(400);
        echo json_encode(['error' => 'Missing bounding box parameters (south, west, north, east)']);
        exit;
    }
    
    if ($south >= $north || $west >= $east) {
        http_response_code(400);
        echo json_encode(['error' => 'Invalid bounding box']);
        exit;
    }
    
    // Optional filters
    $type = isset($_GET['type']) ? $_GET['type'] : null;
    $search = isset($_GET['search']) ? trim($_GET['search']) : null;
    $source = isset($_GET['source']) ? $_GET['source'] : null;
    $minConfidence = isset($_GET['min_confidence']) ? floatval($_GET['min_confidence']) : 0.30;
    $includeClosed = isset($_GET['include_closed']) ? filter_var($_GET['include_closed'], FILTER_VALIDATE_BOOLEAN) : false;
    $limit = min(intval($_GET['limit'] ?? 100), 500);
    $offset = intval($_GET['offset'] ?? 0);
    
    // Build query
    $params = [];
    $whereClauses = ['v.is_active = 1'];
    
    // Bounding box filter
    $whereClauses[] = 'v.lat >= :south AND v.lat <= :north AND v.lng >= :west AND v.lng <= :east';
    $params[':south'] = $south;
    $params[':north'] = $north;
    $params[':west'] = $west;
    $params[':east'] = $east;
    
    // Confidence filter
    $whereClauses[] = 'v.confidence_score >= :min_confidence';
    $params[':min_confidence'] = $minConfidence;
    
    // Operating status filter
    if (!$includeClosed) {
        $whereClauses[] = "v.operating_status = 'open'";
    }
    
    // Type filter
    if ($type) {
        $validTypes = ['restaurant', 'cafe', 'bar', 'pub', 'shop', 'food_truck', 
                       'farmers_market', 'ghost_kitchen', 'pop_up', 'bakery', 'deli', 'ice_cream'];
        if (in_array($type, $validTypes)) {
            $whereClauses[] = 'v.type = :type';
            $params[':type'] = $type;
        }
    }
    
    // Source filter
    if ($source) {
        $whereClauses[] = 'v.source = :source';
        $params[':source'] = $source;
    }
    
    // Search filter
    $searchJoin = '';
    if ($search) {
        // Use full-text search if available, fallback to LIKE
        $whereClauses[] = '(v.name LIKE :search OR v.cuisine LIKE :search OR v.brand LIKE :search OR v.address LIKE :search)';
        $params[':search'] = '%' . $search . '%';
    }
    
    $whereSql = implode(' AND ', $whereClauses);
    
    // Count query for pagination
    $countSql = "SELECT COUNT(*) FROM venues v WHERE $whereSql";
    $countStmt = $pdo->prepare($countSql);
    foreach ($params as $key => $val) {
        $countStmt->bindValue($key, $val);
    }
    $countStmt->execute();
    $totalCount = $countStmt->fetchColumn();
    
    // Main query with prioritization
    // Priority: Government sources > Commercial > Open Data
    $sql = "SELECT 
        v.id,
        v.name,
        v.lat,
        v.lng,
        v.type,
        v.cuisine,
        v.brand,
        v.source,
        v.sub_source,
        v.rating,
        v.rating_count,
        v.price_level as priceLevel,
        v.address,
        v.city,
        v.state,
        v.zip,
        v.county,
        v.phone,
        v.website,
        v.operating_status as operatingStatus,
        v.hours_confirmed as hoursConfirmed,
        v.license_number as licenseNumber,
        v.license_status as licenseStatus,
        v.inspection_score as inspectionScore,
        v.last_inspection_date as lastInspectionDate,
        v.metadata,
        v.confidence_score as confidenceScore,
        v.data_freshness as dataFreshness,
        v.last_updated as lastUpdated,
        v.last_verified as lastVerified,
        
        -- Source priority for ordering (higher = more trustworthy)
        CASE v.source
            WHEN 'dbpr' THEN 10
            WHEN 'orange_county' THEN 10
            WHEN 'miami_dade' THEN 10
            WHEN 'broward_county' THEN 10
            WHEN 'hillsborough_county' THEN 10
            WHEN 'duval_county' THEN 10
            WHEN 'orlando_city' THEN 10
            WHEN 'usda_farmers_market' THEN 9
            WHEN 'nps' THEN 9
            WHEN 'fl_state_parks' THEN 9
            WHEN 'google_places' THEN 7
            WHEN 'yelp' THEN 6
            WHEN 'foursquare' THEN 6
            WHEN 'tripadvisor' THEN 5
            WHEN 'overture' THEN 4
            WHEN 'osm' THEN 3
            ELSE 1
        END as source_priority
        
    FROM venues v
    WHERE $whereSql
    ORDER BY 
        source_priority DESC,
        v.confidence_score DESC,
        v.rating DESC,
        v.name ASC
    LIMIT :limit OFFSET :offset";
    
    $stmt = $pdo->prepare($sql);
    foreach ($params as $key => $val) {
        $stmt->bindValue($key, $val);
    }
    $stmt->bindValue(':limit', $limit, PDO::PARAM_INT);
    $stmt->bindValue(':offset', $offset, PDO::PARAM_INT);
    $stmt->execute();
    
    $venues = [];
    while ($row = $stmt->fetch(PDO::FETCH_ASSOC)) {
        // Parse metadata JSON
        $metadata = json_decode($row['metadata'] ?? '{}', true);
        
        // Clean up the response
        $venue = [
            'id' => $row['id'],
            'name' => $row['name'],
            'lat' => floatval($row['lat']),
            'lng' => floatval($row['lng']),
            'type' => $row['type'],
            'cuisine' => $row['cuisine'] ?? 'Various',
            'brand' => $row['brand'] ?? '',
            'source' => $row['source'],
            'subSource' => $row['sub_source'],
            'sourcePriority' => intval($row['source_priority']),
            'rating' => $row['rating'] ? floatval($row['rating']) : null,
            'ratingCount' => intval($row['rating_count']),
            'priceLevel' => $row['priceLevel'] ? intval($row['priceLevel']) : null,
            'address' => [
                'street' => $row['address'],
                'city' => $row['city'],
                'state' => $row['state'],
                'zip' => $row['zip'],
                'county' => $row['county']
            ],
            'contact' => [
                'phone' => $row['phone'],
                'website' => $row['website']
            ],
            'status' => [
                'operating' => $row['operatingStatus'],
                'hoursConfirmed' => (bool)$row['hoursConfirmed'],
                'licenseNumber' => $row['licenseNumber'],
                'licenseStatus' => $row['licenseStatus']
            ],
            'inspection' => [
                'score' => $row['inspectionScore'] ? floatval($row['inspectionScore']) : null,
                'lastDate' => $row['lastInspectionDate']
            ],
            'quality' => [
                'confidenceScore' => floatval($row['confidenceScore']),
                'dataFreshness' => intval($row['dataFreshness'])
            ],
            'metadata' => $metadata,
            'timestamps' => [
                'lastUpdated' => intval($row['lastUpdated']),
                'lastVerified' => $row['lastVerified'] ? intval($row['lastVerified']) : null
            ]
        ];
        
        $venues[] = $venue;
    }
    
    // Calculate grid cell info for this area
    $centerLat = ($south + $north) / 2;
    $centerLng = ($west + $east) / 2;
    $gridCell = getGridCell($centerLat, $centerLng);
    
    // Get cell freshness info
    $cellStmt = $pdo->prepare("
        SELECT last_fetched, venue_count, coverage_score 
        FROM grid_cells 
        WHERE cell_key = ?
    ");
    $cellStmt->execute([$gridCell]);
    $cellInfo = $cellStmt->fetch();
    
    // Build response
    $response = [
        'success' => true,
        'venues' => $venues,
        'pagination' => [
            'count' => count($venues),
            'total' => intval($totalCount),
            'limit' => $limit,
            'offset' => $offset,
            'hasMore' => ($offset + count($venues)) < $totalCount
        ],
        'filters' => [
            'bounds' => ['south' => $south, 'west' => $west, 'north' => $north, 'east' => $east],
            'type' => $type,
            'search' => $search,
            'source' => $source,
            'minConfidence' => $minConfidence,
            'includeClosed' => $includeClosed
        ],
        'gridCell' => [
            'key' => $gridCell,
            'cached' => $cellInfo ? true : false,
            'lastFetched' => $cellInfo ? intval($cellInfo['last_fetched']) : null,
            'venueCount' => $cellInfo ? intval($cellInfo['venue_count']) : 0,
            'coverageScore' => $cellInfo ? floatval($cellInfo['coverage_score']) : 0.0
        ],
        'sources' => [
            'government' => count(array_filter($venues, fn($v) => in_array($v['source'], ['dbpr', 'orange_county', 'miami_dade', 'broward_county', 'hillsborough_county', 'duval_county', 'orlando_city']))),
            'commercial' => count(array_filter($venues, fn($v) => in_array($v['source'], ['yelp', 'google_places', 'foursquare', 'tripadvisor']))),
            'openData' => count(array_filter($venues, fn($v) => in_array($v['source'], ['overture', 'osm', 'usda_farmers_market'])))
        ],
        'timestamp' => time()
    ];
    
    echo json_encode($response, JSON_PRETTY_PRINT);
    
} catch (Exception $e) {
    http_response_code(500);
    echo json_encode(['error' => 'Database error: ' . $e->getMessage()]);
}

function getGridCell($lat, $lng, $gridSize = 0.02) {
    $gridLat = floor($lat / $gridSize) * $gridSize;
    $gridLng = floor($lng / $gridSize) * $gridSize;
    return sprintf('%.3f,%.3f', $gridLat, $gridLng);
}
