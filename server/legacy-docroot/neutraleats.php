<?php
$config = require 'config.php'; 
ini_set('display_errors', 1);
ini_set('display_startup_errors', 1);
error_reporting(E_ALL);
header('Content-Type: application/json');

// Database Connection Details from config file
$servername = $config['DB_HOST'];
$username = $config['DB_USERNAME'];
$password = $config['DB_PASSWORD'];
$dbname = $config['DB_NAME'];

$conn = new mysqli($servername, $username, $password, $dbname);

// Check connection
if ($conn->connect_error) {
    die(json_encode(array('status' => 'error', 'message' => 'Connection failed: ' . $conn->connect_error)));
}

// Get the bounds from the request body
$inputJSON = file_get_contents('php://input');
$bounds = json_decode($inputJSON, true);

if (isset($bounds['bounds'])) {
    $sql = "SELECT restaurant_id, restaurant_name, latitude, longitude, seat_count, replace(concat(address1 , case when address2 = '' then '' else ' ' end , address2 , ', ',city,', ',state,' ',postal_code),'#130','') as address,primary_phone_number
            FROM eatery
            WHERE latitude IS NOT NULL
              AND latitude BETWEEN ? AND ?
              AND longitude BETWEEN ? AND ?
              AND is_active = 1 -- restaurant is still open
	     order by restaurant_id MOD 2
              limit 300;";

    $stmt = $conn->prepare($sql);
    $stmt->bind_param("dddd", $southWestLat, $northEastLat, $southWestLng, $northEastLng);

    $southWestLat = $bounds['bounds']['southWest']['lat'];
    $northEastLat = $bounds['bounds']['northEast']['lat'];
    $southWestLng = $bounds['bounds']['southWest']['lng'];
    $northEastLng = $bounds['bounds']['northEast']['lng'];

    if (!$stmt->execute()) {
        die(json_encode(array('status' => 'error', 'message' => 'Query failed: ' . $stmt->error)));
    }
    $result = $stmt->get_result();

    $locations = array();
    while ($row = $result->fetch_assoc()) {
        $locations[] = $row;
    }

    echo json_encode($locations);
} else {
    echo json_encode(array('status' => 'error', 'message' => 'No bounds provided'));
}

$conn->close();
?>
