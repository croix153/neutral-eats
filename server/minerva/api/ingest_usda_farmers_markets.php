<?php
/**
 * USDA Farmers Market Directory Ingestion
 * Source: https://www.ams.usda.gov/services/local-regional/farmers-markets
 * API: https://search.ams.usda.gov/farmersmarkets/v1/data.svc/
 * 
 * This fetches all farmers markets nationwide, filters to Florida,
 * and ingests into the Neutral Eats database.
 */

require_once __DIR__ . '/../config/database.php';

class USDAFarmersMarketIngestor {
    private $pdo;
    private $logFile;
    private $apiBase = 'https://search.ams.usda.gov/farmersmarkets/v1/data.svc';
    private $sourceName = 'usda_farmers_market';
    private $syncId;
    
    // Florida bounding box
    private $floridaBounds = [
        'south' => 24.0,
        'north' => 31.0,
        'west' => -87.5,
        'east' => -79.8
    ];
    
    public function __construct($pdo) {
        $this->pdo = $pdo;
        $this->logFile = __DIR__ . '/../logs/usda_ingest.log';
        $this->ensureLogDirectory();
    }
    
    private function ensureLogDirectory() {
        $dir = dirname($this->logFile);
        if (!is_dir($dir)) {
            mkdir($dir, 0755, true);
        }
    }
    
    private function log($message) {
        $line = date('Y-m-d H:i:s') . ' [USDA] ' . $message . PHP_EOL;
        echo $line;
        file_put_contents($this->logFile, $line, FILE_APPEND | LOCK_EX);
    }
    
    private function startSync() {
        $stmt = $this->pdo->prepare("
            INSERT INTO sync_log (source, started_at, status) 
            VALUES (?, UNIX_TIMESTAMP(), 'running')
        ");
        $stmt->execute([$this->sourceName]);
        $this->syncId = $this->pdo->lastInsertId();
        return $this->syncId;
    }
    
    private function endSync($status, $stats = []) {
        $stmt = $this->pdo->prepare("
            UPDATE sync_log 
            SET status = ?, 
                completed_at = UNIX_TIMESTAMP(),
                venues_added = ?,
                venues_updated = ?,
                api_calls = ?
            WHERE id = ?
        ");
        $stmt->execute([
            $status,
            $stats['added'] ?? 0,
            $stats['updated'] ?? 0,
            $stats['api_calls'] ?? 0,
            $this->syncId
        ]);
    }
    
    /**
     * Fetch all farmers markets from USDA API
     */
    public function fetchAllMarkets() {
        $this->log("Starting USDA Farmers Market ingestion...");
        $this->startSync();
        
        $stats = ['added' => 0, 'updated' => 0, 'api_calls' => 0, 'errors' => 0];
        
        try {
            // Step 1: Get zip code search for Florida regions
            // We'll search by major Florida zip codes to get all markets
            $floridaZips = $this->getFloridaZipCodes();
            
            $allMarkets = [];
            $seenIds = [];
            
            foreach ($floridaZips as $zip) {
                $markets = $this->searchByZip($zip);
                $stats['api_calls']++;
                
                foreach ($markets as $market) {
                    $id = $market['id'];
                    if (!isset($seenIds[$id])) {
                        $seenIds[$id] = true;
                        $allMarkets[] = $market;
                    }
                }
                
                // Rate limiting - be nice to the API
                usleep(100000); // 100ms delay
                
                if (count($allMarkets) > 1000) {
                    $this->log("Found " . count($allMarkets) . " markets, processing batch...");
                    $this->processMarkets($allMarkets, $stats);
                    $allMarkets = [];
                }
            }
            
            // Process remaining markets
            if (!empty($allMarkets)) {
                $this->processMarkets($allMarkets, $stats);
            }
            
            $this->log("Ingestion complete. Added: {$stats['added']}, Updated: {$stats['updated']}");
            $this->endSync('success', $stats);
            
        } catch (Exception $e) {
            $this->log("ERROR: " . $e->getMessage());
            $this->endSync('error', $stats);
            throw $e;
        }
        
        return $stats;
    }
    
    /**
     * Search markets by zip code
     */
    private function searchByZip($zip) {
        $url = $this->apiBase . '/zipSearch?zip=' . urlencode($zip);
        
        $ch = curl_init($url);
        curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
        curl_setopt($ch, CURLOPT_TIMEOUT, 30);
        curl_setopt($ch, CURLOPT_FOLLOWLOCATION, true);
        curl_setopt($ch, CURLOPT_USERAGENT, 'NeutralEatsBot/1.0 (Research Project)');
        
        $response = curl_exec($ch);
        $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
        curl_close($ch);
        
        if ($httpCode !== 200 || !$response) {
            $this->log("API error for zip $zip: HTTP $httpCode");
            return [];
        }
        
        $data = json_decode($response, true);
        return $data['results'] ?? [];
    }
    
    /**
     * Get detailed market info
     */
    private function getMarketDetails($marketId) {
        // Check cache first
        $cacheKey = "market_$marketId";
        $cached = $this->getCache($cacheKey);
        if ($cached) {
            return $cached;
        }
        
        $url = $this->apiBase . '/mktDetail?id=' . urlencode($marketId);
        
        $ch = curl_init($url);
        curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
        curl_setopt($ch, CURLOPT_TIMEOUT, 30);
        curl_setopt($ch, CURLOPT_USERAGENT, 'NeutralEatsBot/1.0 (Research Project)');
        
        $response = curl_exec($ch);
        curl_close($ch);
        
        $data = json_decode($response, true);
        $details = $data['marketdetails'] ?? null;
        
        if ($details) {
            // Cache for 7 days
            $this->setCache($cacheKey, $details, 604800);
        }
        
        return $details;
    }
    
    /**
     * Process and store markets
     */
    private function processMarkets($markets, &$stats) {
        foreach ($markets as $market) {
            try {
                $details = $this->getMarketDetails($market['id']);
                
                if (!$details) {
                    continue;
                }
                
                // Parse address to extract components
                $addressParts = $this->parseAddress($details['Address'] ?? '');
                
                // Geocode if we don't have lat/lng
                $lat = $details['lat'] ?? null;
                $lng = $details['lng'] ?? null;
                
                if (!$lat || !$lng) {
                    $coords = $this->geocodeAddress($details['Address']);
                    $lat = $coords['lat'] ?? null;
                    $lng = $coords['lng'] ?? null;
                }
                
                if (!$lat || !$lng) {
                    $this->log("Skipping market '{$market['marketname']}' - no coordinates");
                    continue;
                }
                
                // Check if in Florida
                if (!$this->isInFlorida($lat, $lng)) {
                    continue;
                }
                
                // Prepare venue data
                $venueId = 'usda_fm_' . $market['id'];
                $now = time();
                
                // Parse products
                $products = $this->parseProducts($details['Products'] ?? '');
                
                // Parse schedule
                $schedule = $this->parseSchedule($details['Schedule'] ?? '');
                
                $metadata = [
                    'usda_id' => $market['id'],
                    'products' => $products,
                    'original_address' => $details['Address'] ?? '',
                    'original_schedule' => $details['Schedule'] ?? '',
                    'ingestion_method' => 'usda_api_v1'
                ];
                
                // Check if venue exists
                $stmt = $this->pdo->prepare("SELECT id, last_updated FROM venues WHERE id = ?");
                $stmt->execute([$venueId]);
                $existing = $stmt->fetch(PDO::FETCH_ASSOC);
                
                if ($existing) {
                    // Update
                    $stmt = $this->pdo->prepare("
                        UPDATE venues SET
                            name = ?, lat = ?, lng = ?, address = ?, city = ?, 
                            state = ?, zip = ?, phone = ?, website = ?,
                            operating_status = ?, hours_confirmed = ?, 
                            metadata = ?, last_updated = ?, last_verified = ?,
                            confidence_score = ?
                        WHERE id = ?
                    ");
                    $stmt->execute([
                        $market['marketname'],
                        $lat, $lng,
                        $addressParts['street'] ?? '',
                        $addressParts['city'] ?? '',
                        $addressParts['state'] ?? 'FL',
                        $addressParts['zip'] ?? '',
                        $details['Phone'] ?? null,
                        $this->extractWebsite($details),
                        $this->determineStatus($schedule),
                        true,
                        json_encode($metadata),
                        $now, $now,
                        0.90,
                        $venueId
                    ]);
                    $stats['updated']++;
                } else {
                    // Insert
                    $stmt = $this->pdo->prepare("
                        INSERT INTO venues (
                            id, name, lat, lng, type, source, sub_source, source_id,
                            address, city, state, zip, phone, website,
                            operating_status, hours_confirmed,
                            metadata, last_updated, first_seen, last_verified,
                            confidence_score, is_active, grid_cell
                        ) VALUES (?, ?, ?, ?, 'farmers_market', ?, 'usda_directory', ?,
                            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ");
                    
                    $gridCell = $this->getGridCell($lat, $lng);
                    
                    $stmt->execute([
                        $venueId,
                        $market['marketname'],
                        $lat, $lng,
                        $this->sourceName,
                        $market['id'],
                        $addressParts['street'] ?? '',
                        $addressParts['city'] ?? '',
                        $addressParts['state'] ?? 'FL',
                        $addressParts['zip'] ?? '',
                        $details['Phone'] ?? null,
                        $this->extractWebsite($details),
                        $this->determineStatus($schedule),
                        true,
                        json_encode($metadata),
                        $now, $now, $now,
                        0.90,
                        true,
                        $gridCell
                    ]);
                    $stats['added']++;
                }
                
                // Update grid cell
                $this->updateGridCell($lat, $lng);
                
            } catch (Exception $e) {
                $this->log("Error processing market {$market['id']}: " . $e->getMessage());
                $stats['errors']++;
            }
            
            // Small delay to be polite
            usleep(50000);
        }
    }
    
    /**
     * Parse USDA address format
     */
    private function parseAddress($address) {
        $parts = ['street' => '', 'city' => '', 'state' => 'FL', 'zip' => ''];
        
        if (!$address) return $parts;
        
        // USDA format is typically:
        // "Street Address, City, State Zip" or similar variations
        
        // Try to extract zip
        if (preg_match('/(\d{5}(-\d{4})?)$/', $address, $matches)) {
            $parts['zip'] = $matches[1];
            $address = preg_replace('/\s*\d{5}(-\d{4})?$/', '', $address);
        }
        
        // Try to extract state
        if (preg_match('/,\s*([A-Za-z]{2})\s*,?$/', $address, $matches)) {
            $parts['state'] = strtoupper($matches[1]);
            $address = preg_replace('/,\s*[A-Za-z]{2}\s*,?$/', '', $address);
        }
        
        // Split remaining by comma for city/street
        $segments = array_map('trim', explode(',', $address));
        if (count($segments) >= 2) {
            $parts['city'] = array_pop($segments);
            $parts['street'] = implode(', ', $segments);
        } else {
            $parts['street'] = $address;
        }
        
        return $parts;
    }
    
    /**
     * Parse products string into array
     */
    private function parseProducts($productsStr) {
        if (!$productsStr) return [];
        return array_map('trim', explode(';', $productsStr));
    }
    
    /**
     * Parse schedule string
     */
    private function parseSchedule($scheduleStr) {
        $schedule = [
            'raw' => $scheduleStr,
            'days' => [],
            'times' => []
        ];
        
        if (!$scheduleStr) return $schedule;
        
        // Common patterns: "Tue 10:00 AM - 2:00 PM", "Year-round", "Seasonal"
        $days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
        foreach ($days as $day) {
            if (stripos($scheduleStr, $day) !== false) {
                $schedule['days'][] = $day;
            }
        }
        
        // Extract times
        if (preg_match('/(\d{1,2}:\d{2}\s*[AP]M)/i', $scheduleStr, $matches)) {
            $schedule['times'][] = $matches[1];
        }
        
        return $schedule;
    }
    
    /**
     * Determine operating status from schedule
     */
    private function determineStatus($schedule) {
        $raw = strtolower($schedule['raw'] ?? '');
        
        if (strpos($raw, 'closed') !== false) {
            return 'temporarily_closed';
        }
        if (strpos($raw, 'seasonal') !== false) {
            return 'seasonal';
        }
        return 'open';
    }
    
    /**
     * Extract website from details
     */
    private function extractWebsite($details) {
        // Website might be in various fields
        if (!empty($details['Website'])) {
            return $details['Website'];
        }
        // Sometimes in Facebook or other social
        if (!empty($details['Facebook'])) {
            return $details['Facebook'];
        }
        return null;
    }
    
    /**
     * Geocode address using Nominatim (OSM)
     */
    private function geocodeAddress($address) {
        if (!$address) return null;
        
        $url = 'https://nominatim.openstreetmap.org/search?format=json&q=' . 
               urlencode($address . ', Florida, USA') . '&limit=1';
        
        $ch = curl_init($url);
        curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
        curl_setopt($ch, CURLOPT_TIMEOUT, 10);
        curl_setopt($ch, CURLOPT_USERAGENT, 'NeutralEatsBot/1.0');
        
        $response = curl_exec($ch);
        curl_close($ch);
        
        $data = json_decode($response, true);
        
        if (!empty($data[0])) {
            return [
                'lat' => floatval($data[0]['lat']),
                'lng' => floatval($data[0]['lon'])
            ];
        }
        
        return null;
    }
    
    /**
     * Check if coordinates are in Florida
     */
    private function isInFlorida($lat, $lng) {
        return (
            $lat >= $this->floridaBounds['south'] &&
            $lat <= $this->floridaBounds['north'] &&
            $lng >= $this->floridaBounds['west'] &&
            $lng <= $this->floridaBounds['east']
        );
    }
    
    /**
     * Get grid cell key
     */
    private function getGridCell($lat, $lng, $gridSize = 0.04) {
        $gridLat = floor($lat / $gridSize) * $gridSize;
        $gridLng = floor($lng / $gridSize) * $gridSize;
        return sprintf('%.3f,%.3f', $gridLat, $gridLng);
    }
    
    /**
     * Update grid cell tracking
     */
    private function updateGridCell($lat, $lng) {
        $cellKey = $this->getGridCell($lat, $lng);
        
        $stmt = $this->pdo->prepare("
            INSERT INTO grid_cells (cell_key, lat_min, lat_max, lng_min, lng_max, venue_count, last_fetched)
            VALUES (?, ?, ?, ?, ?, 1, UNIX_TIMESTAMP())
            ON DUPLICATE KEY UPDATE
                venue_count = venue_count + 1,
                last_fetched = UNIX_TIMESTAMP()
        ");
        
        $gridSize = 0.04;
        $latMin = floor($lat / $gridSize) * $gridSize;
        $lngMin = floor($lng / $gridSize) * $gridSize;
        
        $stmt->execute([
            $cellKey,
            $latMin,
            $latMin + $gridSize,
            $lngMin,
            $lngMin + $gridSize
        ]);
    }
    
    /**
     * Get cache
     */
    private function getCache($key) {
        $stmt = $this->pdo->prepare("
            SELECT response_data FROM api_cache 
            WHERE source = ? AND cache_key = ? AND expires_at > UNIX_TIMESTAMP()
        ");
        $stmt->execute([$this->sourceName, $key]);
        $result = $stmt->fetchColumn();
        return $result ? json_decode($result, true) : null;
    }
    
    /**
     * Set cache
     */
    private function setCache($key, $data, $ttl) {
        $stmt = $this->pdo->prepare("
            INSERT INTO api_cache (source, cache_key, response_data, expires_at, created_at)
            VALUES (?, ?, ?, UNIX_TIMESTAMP() + ?, UNIX_TIMESTAMP())
            ON DUPLICATE KEY UPDATE
                response_data = VALUES(response_data),
                expires_at = VALUES(expires_at)
        ");
        $stmt->execute([$this->sourceName, $key, json_encode($data), $ttl]);
    }
    
    /**
     * Get representative Florida zip codes for searching
     */
    private function getFloridaZipCodes() {
        // Major metro zip codes to cover all of Florida
        return [
            // Orlando area
            '32801', '32806', '32811', '32819', '32822', '32835',
            // Tampa area  
            '33602', '33606', '33609', '33614', '33629',
            // Miami area
            '33101', '33130', '33133', '33139', '33155',
            // Jacksonville
            '32202', '32204', '32207', '32210', '32225',
            // Tallahassee
            '32301', '32303', '32308',
            // Gainesville
            '32601', '32605', '32608',
            // West Palm Beach
            '33401', '33405', '33411',
            // Fort Lauderdale
            '33301', '33304', '33308',
            // Sarasota
            '34236', '34237', '34243',
            // Naples
            '34102', '34104', '34112',
            // Pensacola
            '32501', '32503', '32514',
            // Melbourne
            '32901', '32904', '32935',
            // Daytona
            '32114', '32118',
            // Ocala
            '34471', '34474',
            // Lakeland
            '33803', '33813',
            // Fort Myers
            '33901', '33907',
            // Key West
            '33040',
            // Panama City
            '32401',
            // St. Augustine
            '32084'
        ];
    }
}

// CLI execution
if (php_sapi_name() === 'cli') {
    require_once __DIR__ . '/../config/database.php';
    $pdo = getDatabaseConnection();
    $ingestor = new USDAFarmersMarketIngestor($pdo);
    $stats = $ingestor->fetchAllMarkets();
    echo "\n=== USDA Farmers Market Ingestion Complete ===\n";
    echo "Added: {$stats['added']}\n";
    echo "Updated: {$stats['updated']}\n";
    echo "API Calls: {$stats['api_calls']}\n";
    echo "Errors: {$stats['errors']}\n";
}
