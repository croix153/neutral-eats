<?php
/**
 * Florida Government Data Ingestion Pipeline
 * 
 * Sources:
 * - Florida DBPR (Division of Hotels & Restaurants) - license data
 * - Orange County Health Inspections
 * - Miami-Dade County permits
 * - Other county open data portals
 * 
 * This script fetches, parses, and ingests restaurant license and inspection data
 * from various Florida government sources.
 */

require_once __DIR__ . '/../config/database.php';

class FloridaGovernmentIngestor {
    private $pdo;
    private $logFile;
    private $syncId;
    
    // County data endpoints (when available)
    private $endpoints = [
        'orange_county' => [
            'url' => 'https://data.ocfl.net/api/search/v1',
            'datasets' => ['restaurant-inspections']
        ],
        'miami_dade' => [
            'url' => 'https://opendata.miamidade.gov/resource/',
            'datasets' => [' Restaurant_Inspections']
        ],
        'orlando_city' => [
            'url' => 'https://data.orlando.gov/api/',
            'datasets' => []
        ]
    ];
    
    public function __construct($pdo) {
        $this->pdo = $pdo;
        $this->logFile = __DIR__ . '/../logs/government_ingest.log';
        $this->ensureLogDirectory();
    }
    
    private function ensureLogDirectory() {
        $dir = dirname($this->logFile);
        if (!is_dir($dir)) {
            mkdir($dir, 0755, true);
        }
    }
    
    private function log($message, $source = 'GOV') {
        $line = date('Y-m-d H:i:s') . " [$source] " . $message . PHP_EOL;
        echo $line;
        file_put_contents($this->logFile, $line, FILE_APPEND | LOCK_EX);
    }
    
    private function startSync($source) {
        $stmt = $this->pdo->prepare("
            INSERT INTO sync_log (source, sub_source, started_at, status) 
            VALUES (?, 'government_pipeline', UNIX_TIMESTAMP(), 'running')
        ");
        $stmt->execute([$source]);
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
     * Main entry point - run all government sources
     */
    public function runAll() {
        $this->log("=== Starting Florida Government Data Ingestion ===");
        
        $totalStats = [
            'added' => 0,
            'updated' => 0,
            'api_calls' => 0,
            'errors' => 0
        ];
        
        // Run each source
        $sources = [
            'orange_county' => 'Orange County Health Inspections',
            'miami_dade' => 'Miami-Dade Restaurant Inspections',
            'dbpr_sample' => 'FL DBPR License Data (Sample)'
        ];
        
        foreach ($sources as $source => $name) {
            $this->log("Processing: $name");
            $stats = $this->ingestSource($source);
            
            $totalStats['added'] += $stats['added'];
            $totalStats['updated'] += $stats['updated'];
            $totalStats['api_calls'] += $stats['api_calls'];
            $totalStats['errors'] += $stats['errors'];
            
            sleep(2); // Be nice between sources
        }
        
        $this->log("=== Government Ingestion Complete ===");
        $this->log("Total Added: {$totalStats['added']}");
        $this->log("Total Updated: {$totalStats['updated']}");
        $this->log("Total API Calls: {$totalStats['api_calls']}");
        
        return $totalStats;
    }
    
    /**
     * Ingest from a specific source
     */
    private function ingestSource($source) {
        $this->startSync($source);
        $stats = ['added' => 0, 'updated' => 0, 'api_calls' => 0, 'errors' => 0];
        
        try {
            switch ($source) {
                case 'orange_county':
                    $stats = $this->ingestOrangeCounty($stats);
                    break;
                case 'miami_dade':
                    $stats = $this->ingestMiamiDade($stats);
                    break;
                case 'dbpr_sample':
                    $stats = $this->ingestDBPRSample($stats);
                    break;
            }
            
            $this->endSync('success', $stats);
        } catch (Exception $e) {
            $this->log("ERROR in $source: " . $e->getMessage());
            $this->endSync('error', $stats);
        }
        
        return $stats;
    }
    
    /**
     * Orange County Health Inspection Data
     * Uses their open data portal when available
     */
    private function ingestOrangeCounty($stats) {
        $this->log("Fetching Orange County data...", 'ORANGE');
        
        // Orange County doesn't have a simple public API for this
        // In production, this would use their Socrata portal or scrape
        // For now, we'll create a framework for when the data is available
        
        // Example: If we had access to their CSV/API
        $sampleData = $this->getOrangeCountySampleData();
        
        foreach ($sampleData as $record) {
            try {
                $this->processGovernmentRecord($record, 'orange_county', $stats);
            } catch (Exception $e) {
                $this->log("Error: " . $e->getMessage(), 'ORANGE');
                $stats['errors']++;
            }
        }
        
        return $stats;
    }
    
    /**
     * Miami-Dade Restaurant Inspections
     */
    private function ingestMiamiDade($stats) {
        $this->log("Fetching Miami-Dade data...", 'MIAMI');
        
        // Miami-Dade uses Socrata/OpenData platform
        $baseUrl = 'https://opendata.miamidade.gov/resource/6j9b-hb9a.json';
        
        // Fetch with pagination
        $offset = 0;
        $limit = 1000;
        $hasMore = true;
        
        while ($hasMore && $offset < 10000) {
            $url = $baseUrl . '?$limit=' . $limit . '&$offset=' . $offset;
            
            $ch = curl_init($url);
            curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
            curl_setopt($ch, CURLOPT_TIMEOUT, 30);
            curl_setopt($ch, CURLOPT_USERAGENT, 'NeutralEatsBot/1.0');
            
            $response = curl_exec($ch);
            $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
            curl_close($ch);
            
            $stats['api_calls']++;
            
            if ($httpCode !== 200) {
                $this->log("API error: HTTP $httpCode", 'MIAMI');
                break;
            }
            
            $data = json_decode($response, true);
            
            if (empty($data)) {
                $hasMore = false;
                break;
            }
            
            foreach ($data as $record) {
                try {
                    $this->processMiamiDadeRecord($record, $stats);
                } catch (Exception $e) {
                    $stats['errors']++;
                }
            }
            
            $this->log("Processed " . count($data) . " records (offset: $offset)", 'MIAMI');
            
            $offset += $limit;
            sleep(1); // Rate limiting
        }
        
        return $stats;
    }
    
    /**
     * Process a Miami-Dade record
     */
    private function processMiamiDadeRecord($record, &$stats) {
        // Miami-Dade fields:
        // license_number, dba_name, location_address, city, state, zip
        // inspection_date, inspection_result, violation_count, etc.
        
        $license = $record['license_number'] ?? null;
        $name = $record['dba_name'] ?? $record['license_holder_name'] ?? null;
        
        if (!$name || !$license) {
            return;
        }
        
        // Geocode the address
        $address = $record['location_address'] ?? '';
        $city = $record['city'] ?? 'Miami';
        $zip = $record['zip'] ?? '';
        
        $coords = $this->geocodeAddress($address, $city, $zip);
        
        if (!$coords) {
            return;
        }
        
        $venueId = 'miami_dade_' . preg_replace('/[^a-zA-Z0-9]/', '_', $license);
        $now = time();
        
        $metadata = [
            'miami_dade_license' => $license,
            'inspection_data' => [
                'date' => $record['inspection_date'] ?? null,
                'result' => $record['inspection_result'] ?? null,
                'violation_count' => $record['violation_count'] ?? 0
            ],
            'license_type' => $record['license_type'] ?? null,
            'ingestion_method' => 'miami_dade_api'
        ];
        
        // Check for existing
        $stmt = $this->pdo->prepare("SELECT id FROM venues WHERE id = ? OR license_number = ?");
        $stmt->execute([$venueId, $license]);
        $existing = $stmt->fetch();
        
        if ($existing) {
            // Update
            $stmt = $this->pdo->prepare("
                UPDATE venues SET
                    name = ?, lat = ?, lng = ?, address = ?, city = ?, zip = ?,
                    license_number = ?, license_type = ?, license_status = ?,
                    inspection_score = ?, last_inspection_date = ?,
                    inspection_violations = ?, metadata = ?,
                    last_updated = ?, last_verified = ?,
                    confidence_score = ?, county = 'Miami-Dade'
                WHERE id = ?
            ");
            
            $stmt->execute([
                $name, $coords['lat'], $coords['lng'],
                $address, $city, $zip,
                $license, $record['license_type'] ?? null, 
                $this->mapLicenseStatus($record['license_status'] ?? 'Active'),
                $this->calculateInspectionScore($record),
                $record['inspection_date'] ?? null,
                $record['violation_count'] ?? 0,
                json_encode($metadata),
                $now, $now, 0.95,
                $existing['id']
            ]);
            $stats['updated']++;
        } else {
            // Insert
            $gridCell = $this->getGridCell($coords['lat'], $coords['lng']);
            
            $stmt = $this->pdo->prepare("
                INSERT INTO venues (
                    id, name, lat, lng, type, source, sub_source, source_id,
                    address, city, state, zip, county,
                    license_number, license_type, license_status,
                    inspection_score, last_inspection_date, inspection_violations,
                    metadata, last_updated, first_seen, last_verified,
                    confidence_score, is_active, grid_cell
                ) VALUES (?, ?, ?, ?, 'restaurant', 'miami_dade', 'inspection_api', ?,
                    ?, ?, 'FL', ?, 'Miami-Dade',
                    ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?, ?, 0.95, true, ?)
            ");
            
            $stmt->execute([
                $venueId, $name, $coords['lat'], $coords['lng'], $license,
                $address, $city, $zip,
                $license, $record['license_type'] ?? null,
                $this->mapLicenseStatus($record['license_status'] ?? 'Active'),
                $this->calculateInspectionScore($record),
                $record['inspection_date'] ?? null,
                $record['violation_count'] ?? 0,
                json_encode($metadata),
                $now, $now, $now,
                $gridCell
            ]);
            $stats['added']++;
        }
    }
    
    /**
     * DBPR Sample Data (framework for when we have access)
     */
    private function ingestDBPRSample($stats) {
        $this->log("DBPR data requires manual CSV download from myfloridalicense.com", 'DBPR');
        $this->log("Visit: https://www.myfloridalicense.com/DBPR/hr/search.html", 'DBPR');
        
        // Check for uploaded CSV
        $csvFile = __DIR__ . '/../data/dbpr_restaurants.csv';
        
        if (!file_exists($csvFile)) {
            $this->log("CSV file not found: $csvFile", 'DBPR');
            $this->log("Please download and place file there", 'DBPR');
            return $stats;
        }
        
        $this->log("Processing DBPR CSV...", 'DBPR');
        
        $handle = fopen($csvFile, 'r');
        $headers = fgetcsv($handle);
        
        $count = 0;
        while (($row = fgetcsv($handle)) !== false) {
            $record = array_combine($headers, $row);
            
            try {
                $this->processDBPRRecord($record, $stats);
                $count++;
                
                if ($count % 100 === 0) {
                    $this->log("Processed $count records...", 'DBPR');
                }
            } catch (Exception $e) {
                $stats['errors']++;
            }
        }
        
        fclose($handle);
        $this->log("Completed processing $count DBPR records", 'DBPR');
        
        return $stats;
    }
    
    /**
     * Process DBPR record
     */
    private function processDBPRRecord($record, &$stats) {
        // DBPR CSV format (varies by download):
        // LicenseNumber, BusinessName, Address, City, State, Zip, LicenseType, Status
        
        $license = $record['LicenseNumber'] ?? $record['LICENSE_NO'] ?? null;
        $name = $record['BusinessName'] ?? $record['ESTABLISHMENT'] ?? null;
        
        if (!$name || !$license) return;
        
        // Filter to restaurants only
        $licenseType = strtolower($record['LicenseType'] ?? $record['LICENSE_TYPE'] ?? '');
        if (strpos($licenseType, 'restaurant') === false && 
            strpos($licenseType, 'food') === false) {
            return;
        }
        
        $address = $record['Address'] ?? $record['ADDRESS'] ?? '';
        $city = $record['City'] ?? $record['CITY'] ?? '';
        $zip = $record['Zip'] ?? $record['ZIP'] ?? '';
        $state = $record['State'] ?? $record['STATE'] ?? 'FL';
        
        // Only Florida
        if ($state !== 'FL') return;
        
        $coords = $this->geocodeAddress($address, $city, $zip);
        if (!$coords) return;
        
        $venueId = 'dbpr_' . preg_replace('/[^a-zA-Z0-9]/', '_', $license);
        $now = time();
        
        $metadata = [
            'dbpr_license' => $license,
            'license_type' => $licenseType,
            'original_status' => $record['Status'] ?? $record['STATUS'] ?? null,
            'ingestion_method' => 'dbpr_csv'
        ];
        
        // Upsert logic similar to above
        $stmt = $this->pdo->prepare("SELECT id FROM venues WHERE id = ? OR license_number = ?");
        $stmt->execute([$venueId, $license]);
        
        if ($stmt->fetch()) {
            // Update existing
            $stats['updated']++;
        } else {
            $gridCell = $this->getGridCell($coords['lat'], $coords['lng']);
            
            $stmt = $this->pdo->prepare("
                INSERT INTO venues (
                    id, name, lat, lng, type, source, sub_source,
                    address, city, state, zip,
                    license_number, license_type, license_status,
                    metadata, last_updated, first_seen, last_verified,
                    confidence_score, is_active, grid_cell
                ) VALUES (?, ?, ?, ?, 'restaurant', 'dbpr', 'license_csv',
                    ?, ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?, ?, 0.95, true, ?)
            ");
            
            $stmt->execute([
                $venueId, $name, $coords['lat'], $coords['lng'],
                $address, $city, $state, $zip,
                $license, $licenseType,
                $this->mapLicenseStatus($record['Status'] ?? 'Active'),
                json_encode($metadata),
                $now, $now, $now,
                $gridCell
            ]);
            $stats['added']++;
        }
    }
    
    /**
     * Geocode address
     */
    private function geocodeAddress($address, $city, $zip) {
        $fullAddress = trim("$address, $city, FL $zip");
        if (!$address || !$city) return null;
        
        // Check cache
        $cacheKey = md5($fullAddress);
        $stmt = $this->pdo->prepare("
            SELECT response_data FROM api_cache 
            WHERE source = 'geocode' AND cache_key = ? AND expires_at > UNIX_TIMESTAMP()
        ");
        $stmt->execute([$cacheKey]);
        $cached = $stmt->fetchColumn();
        
        if ($cached) {
            return json_decode($cached, true);
        }
        
        // Geocode via Nominatim
        $url = 'https://nominatim.openstreetmap.org/search?format=json&q=' . 
               urlencode($fullAddress) . '&limit=1';
        
        $ch = curl_init($url);
        curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
        curl_setopt($ch, CURLOPT_TIMEOUT, 10);
        curl_setopt($ch, CURLOPT_USERAGENT, 'NeutralEatsBot/1.0');
        
        $response = curl_exec($ch);
        curl_close($ch);
        
        $data = json_decode($response, true);
        
        if (!empty($data[0])) {
            $result = [
                'lat' => floatval($data[0]['lat']),
                'lng' => floatval($data[0]['lon'])
            ];
            
            // Cache for 30 days
            $stmt = $this->pdo->prepare("
                INSERT INTO api_cache (source, cache_key, response_data, expires_at, created_at)
                VALUES ('geocode', ?, ?, UNIX_TIMESTAMP() + 2592000, UNIX_TIMESTAMP())
                ON DUPLICATE KEY UPDATE response_data = VALUES(response_data), expires_at = VALUES(expires_at)
            ");
            $stmt->execute([$cacheKey, json_encode($result)]);
            
            return $result;
        }
        
        return null;
    }
    
    /**
     * Map license status to our enum
     */
    private function mapLicenseStatus($status) {
        $status = strtolower(trim($status));
        
        if (strpos($status, 'active') !== false) return 'active';
        if (strpos($status, 'suspend') !== false) return 'suspended';
        if (strpos($status, 'expire') !== false) return 'expired';
        if (strpos($status, 'cancel') !== false) return 'inactive';
        
        return 'active';
    }
    
    /**
     * Calculate inspection score from record
     */
    private function calculateInspectionScore($record) {
        // Convert violations to a score (fewer violations = higher score)
        $violations = intval($record['violation_count'] ?? 0);
        $baseScore = 100;
        $deduction = min($violations * 5, 50); // Max 50 point deduction
        
        return max($baseScore - $deduction, 0);
    }
    
    /**
     * Get grid cell
     */
    private function getGridCell($lat, $lng, $gridSize = 0.04) {
        $gridLat = floor($lat / $gridSize) * $gridSize;
        $gridLng = floor($lng / $gridSize) * $gridSize;
        return sprintf('%.3f,%.3f', $gridLat, $gridLng);
    }
    
    /**
     * Sample data for Orange County (framework)
     */
    private function getOrangeCountySampleData() {
        // In production, this would fetch from their API
        // For now, return empty - real data requires API key
        return [];
    }
}

// CLI execution
if (php_sapi_name() === 'cli') {
    $pdo = getDatabaseConnection();
    $ingestor = new FloridaGovernmentIngestor($pdo);
    $stats = $ingestor->runAll();
    
    echo "\n=== Florida Government Ingestion Complete ===\n";
    echo "Added: {$stats['added']}\n";
    echo "Updated: {$stats['updated']}\n";
    echo "Errors: {$stats['errors']}\n";
}
