<?php
/**
 * Neutral Eats Deduplication & Enrichment Pipeline
 * 
 * This script:
 * 1. Identifies duplicate venues across sources
 * 2. Merges data from multiple sources
 * 3. Selects best attributes for canonical records
 * 4. Updates confidence scores
 */

require_once __DIR__ . '/../config/database.php';

class VenueDeduplicator {
    private $pdo;
    private $logFile;
    
    // Distance threshold for considering venues the same (in km)
    private $distanceThreshold = 0.05; // 50 meters
    
    // Name similarity threshold
    private $nameSimilarityThreshold = 0.80;
    
    public function __construct($pdo) {
        $this->pdo = $pdo;
        $this->logFile = __DIR__ . '/../logs/dedup.log';
        $this->ensureLogDirectory();
    }
    
    private function ensureLogDirectory() {
        $dir = dirname($this->logFile);
        if (!is_dir($dir)) {
            mkdir($dir, 0755, true);
        }
    }
    
    private function log($message) {
        $line = date('Y-m-d H:i:s') . ' [DEDUP] ' . $message . PHP_EOL;
        echo $line;
        file_put_contents($this->logFile, $line, FILE_APPEND | LOCK_EX);
    }
    
    /**
     * Main deduplication run
     */
    public function run() {
        $this->log("=== Starting Deduplication Pipeline ===");
        
        $stats = [
            'clusters_found' => 0,
            'venues_merged' => 0,
            'records_updated' => 0
        ];
        
        // Step 1: Find duplicates by location proximity
        $this->log("Step 1: Finding location-based duplicates...");
        $locationDups = $this->findLocationDuplicates();
        $stats['clusters_found'] += count($locationDups);
        
        // Step 2: Verify name similarity for location matches
        $this->log("Step 2: Verifying name matches...");
        $verifiedClusters = $this->verifyNameMatches($locationDups);
        
        // Step 3: Merge verified clusters
        $this->log("Step 3: Merging verified clusters...");
        foreach ($verifiedClusters as $cluster) {
            $this->mergeCluster($cluster, $stats);
        }
        
        // Step 4: Find and flag license number duplicates
        $this->log("Step 4: Checking license duplicates...");
        $licenseDups = $this->findLicenseDuplicates();
        foreach ($licenseDups as $dup) {
            $this->mergeByLicense($dup, $stats);
        }
        
        // Step 5: Update confidence scores
        $this->log("Step 5: Recalculating confidence scores...");
        $this->updateConfidenceScores();
        
        $this->log("=== Deduplication Complete ===");
        $this->log("Clusters found: {$stats['clusters_found']}");
        $this->log("Venues merged: {$stats['venues_merged']}");
        $this->log("Records updated: {$stats['records_updated']}");
        
        return $stats;
    }
    
    /**
     * Find venues that are close to each other
     */
    private function findLocationDuplicates() {
        $clusters = [];
        
        // Get all active venues
        $stmt = $this->pdo->query("
            SELECT id, name, lat, lng, source, license_number, address
            FROM venues
            WHERE is_active = 1
            ORDER BY lat, lng
        ");
        
        $venues = $stmt->fetchAll();
        $this->log("Checking " . count($venues) . " venues for duplicates...");
        
        // Simple grid-based clustering
        $gridSize = 0.001; // ~100m
        $grid = [];
        
        foreach ($venues as $venue) {
            $gridKey = sprintf('%.3f,%.3f',
                floor($venue['lat'] / $gridSize) * $gridSize,
                floor($venue['lng'] / $gridSize) * $gridSize
            );
            
            if (!isset($grid[$gridKey])) {
                $grid[$gridKey] = [];
            }
            $grid[$gridKey][] = $venue;
        }
        
        // Find clusters within each grid cell
        foreach ($grid as $cellVenues) {
            if (count($cellVenues) < 2) continue;
            
            // Compare all pairs in this cell
            for ($i = 0; $i < count($cellVenues); $i++) {
                for ($j = $i + 1; $j < count($cellVenues); $j++) {
                    $v1 = $cellVenues[$i];
                    $v2 = $cellVenues[$j];
                    
                    // Skip if already processed
                    if ($v1['id'] === $v2['id']) continue;
                    
                    $distance = $this->calculateDistance(
                        $v1['lat'], $v1['lng'],
                        $v2['lat'], $v2['lng']
                    );
                    
                    if ($distance <= $this->distanceThreshold) {
                        $clusters[] = [$v1, $v2];
                    }
                }
            }
        }
        
        return $clusters;
    }
    
    /**
     * Calculate distance between two points (Haversine formula)
     */
    private function calculateDistance($lat1, $lng1, $lat2, $lng2) {
        $earthRadius = 6371; // km
        
        $dLat = deg2rad($lat2 - $lat1);
        $dLng = deg2rad($lng2 - $lng1);
        
        $a = sin($dLat/2) * sin($dLat/2) +
             cos(deg2rad($lat1)) * cos(deg2rad($lat2)) *
             sin($dLng/2) * sin($dLng/2);
        
        $c = 2 * atan2(sqrt($a), sqrt(1-$a));
        
        return $earthRadius * $c;
    }
    
    /**
     * Verify name similarity for potential duplicates
     */
    private function verifyNameMatches($clusters) {
        $verified = [];
        
        foreach ($clusters as $cluster) {
            $v1 = $cluster[0];
            $v2 = $cluster[1];
            
            $similarity = $this->calculateNameSimilarity($v1['name'], $v2['name']);
            
            if ($similarity >= $this->nameSimilarityThreshold) {
                $verified[] = $cluster;
            } elseif ($similarity >= 0.60) {
                // Flag for manual review if moderately similar
                $this->flagForReview($v1, $v2, $similarity);
            }
        }
        
        return $verified;
    }
    
    /**
     * Calculate string similarity (Jaccard index on word sets)
     */
    private function calculateNameSimilarity($name1, $name2) {
        $name1 = strtolower(trim($name1));
        $name2 = strtolower(trim($name2));
        
        // Remove common suffixes
        $name1 = preg_replace('/\s+(restaurant|cafe|bar|grill|kitchen|house)$/i', '', $name1);
        $name2 = preg_replace('/\s+(restaurant|cafe|bar|grill|kitchen|house)$/i', '', $name2);
        
        // Split into words
        $words1 = array_filter(explode(' ', $name1));
        $words2 = array_filter(explode(' ', $name2));
        
        if (empty($words1) || empty($words2)) {
            return 0;
        }
        
        // Calculate Jaccard similarity
        $intersection = count(array_intersect($words1, $words2));
        $union = count(array_unique(array_merge($words1, $words2)));
        
        return $union > 0 ? $intersection / $union : 0;
    }
    
    /**
     * Flag potential duplicates for manual review
     */
    private function flagForReview($v1, $v2, $similarity) {
        $stmt = $this->pdo->prepare("
            INSERT INTO duplicate_clusters 
            (canonical_venue_id, duplicate_venue_id, match_score, match_reason, resolution)
            VALUES (?, ?, ?, ?, 'pending')
            ON DUPLICATE KEY UPDATE
                match_score = VALUES(match_score),
                match_reason = VALUES(match_reason)
        ");
        
        $stmt->execute([
            $v1['id'],
            $v2['id'],
            $similarity,
            'name_similarity:' . round($similarity, 2)
        ]);
    }
    
    /**
     * Merge a cluster of venues
     */
    private function mergeCluster($cluster, &$stats) {
        $v1 = $cluster[0]; // Primary (typically government source)
        $v2 = $cluster[1]; // Secondary
        
        // Determine which record to keep as canonical
        // Priority: Government sources > Commercial > Open Data > Crowdsourced
        $sourcePriority = [
            'dbpr' => 10,
            'orange_county' => 10,
            'miami_dade' => 10,
            'broward_county' => 10,
            'hillsborough_county' => 10,
            'duval_county' => 10,
            'orlando_city' => 10,
            'usda_farmers_market' => 9,
            'nps' => 9,
            'fl_state_parks' => 9,
            'google_places' => 7,
            'yelp' => 6,
            'foursquare' => 6,
            'tripadvisor' => 5,
            'overture' => 4,
            'osm' => 3
        ];
        
        $p1 = $sourcePriority[$v1['source']] ?? 1;
        $p2 = $sourcePriority[$v2['source']] ?? 1;
        
        if ($p1 >= $p2) {
            $canonical = $v1;
            $duplicate = $v2;
        } else {
            $canonical = $v2;
            $duplicate = $v1;
        }
        
        // Merge data: take best attributes from both
        $merged = $this->mergeAttributes($canonical, $duplicate);
        
        // Update canonical record
        $stmt = $this->pdo->prepare("
            UPDATE venues SET
                rating = COALESCE(?, rating),
                rating_count = GREATEST(rating_count, ?),
                price_level = COALESCE(?, price_level),
                phone = COALESCE(?, phone),
                website = COALESCE(?, website),
                hours = COALESCE(?, hours),
                license_number = COALESCE(?, license_number),
                license_status = COALESCE(?, license_status),
                inspection_score = COALESCE(?, inspection_score),
                metadata = ?,
                last_updated = UNIX_TIMESTAMP(),
                confidence_score = LEAST(confidence_score + 0.10, 1.0)
            WHERE id = ?
        ");
        
        $stmt->execute([
            $merged['rating'],
            $merged['rating_count'],
            $merged['price_level'],
            $merged['phone'],
            $merged['website'],
            $merged['hours'],
            $merged['license_number'],
            $merged['license_status'],
            $merged['inspection_score'],
            json_encode($merged['metadata']),
            $canonical['id']
        ]);
        
        // Mark duplicate as inactive
        $stmt = $this->pdo->prepare("
            UPDATE venues 
            SET is_active = 0, 
                metadata = JSON_SET(COALESCE(metadata, '{}'), '$.merged_into', ?, '$.merge_date', UNIX_TIMESTAMP())
            WHERE id = ?
        ");
        $stmt->execute([$canonical['id'], $duplicate['id']]);
        
        // Record the merge
        $stmt = $this->pdo->prepare("
            INSERT INTO duplicate_clusters 
            (canonical_venue_id, duplicate_venue_id, match_score, match_reason, resolution, resolved_at)
            VALUES (?, ?, 1.0, 'automatic_merge', 'merged', UNIX_TIMESTAMP())
            ON DUPLICATE KEY UPDATE
                resolution = 'merged',
                resolved_at = UNIX_TIMESTAMP()
        ");
        $stmt->execute([$canonical['id'], $duplicate['id']]);
        
        $stats['venues_merged']++;
        $stats['records_updated'] += 2;
    }
    
    /**
     * Merge attributes from two venue records
     */
    private function mergeAttributes($canonical, $duplicate) {
        $merged = [];
        
        // Fetch full records
        $stmt = $this->pdo->prepare("SELECT * FROM venues WHERE id IN (?, ?)");
        $stmt->execute([$canonical['id'], $duplicate['id']]);
        $records = $stmt->fetchAll(PDO::FETCH_ASSOC);
        
        $r1 = $records[0]['id'] === $canonical['id'] ? $records[0] : $records[1];
        $r2 = $records[0]['id'] === $duplicate['id'] ? $records[0] : $records[1];
        
        // Take best rating
        if (($r1['rating'] ?? 0) > ($r2['rating'] ?? 0)) {
            $merged['rating'] = $r1['rating'];
            $merged['rating_count'] = $r1['rating_count'];
        } else {
            $merged['rating'] = $r2['rating'];
            $merged['rating_count'] = $r2['rating_count'];
        }
        
        // Take best price level
        $merged['price_level'] = $r1['price_level'] ?? $r2['price_level'];
        
        // Take most complete phone
        $merged['phone'] = !empty($r1['phone']) ? $r1['phone'] : $r2['phone'];
        
        // Take most complete website
        $merged['website'] = !empty($r1['website']) ? $r1['website'] : $r2['website'];
        
        // Take hours from source that has them
        $merged['hours'] = !empty($r1['hours']) ? $r1['hours'] : $r2['hours'];
        
        // Government license data takes priority
        $merged['license_number'] = !empty($r1['license_number']) ? $r1['license_number'] : $r2['license_number'];
        $merged['license_status'] = !empty($r1['license_status']) ? $r1['license_status'] : $r2['license_status'];
        $merged['inspection_score'] = !empty($r1['inspection_score']) ? $r1['inspection_score'] : $r2['inspection_score'];
        
        // Merge metadata
        $m1 = json_decode($r1['metadata'] ?? '{}', true);
        $m2 = json_decode($r2['metadata'] ?? '{}', true);
        $merged['metadata'] = array_merge($m1, $m2, [
            'merged_sources' => [$r1['source'], $r2['source']],
            'merge_date' => date('Y-m-d H:i:s')
        ]);
        
        return $merged;
    }
    
    /**
     * Find duplicates by license number
     */
    private function findLicenseDuplicates() {
        $stmt = $this->pdo->query("
            SELECT license_number, COUNT(*) as count, 
                   GROUP_CONCAT(id) as venue_ids
            FROM venues
            WHERE license_number IS NOT NULL 
              AND license_number != ''
              AND is_active = 1
            GROUP BY license_number
            HAVING count > 1
        ");
        
        return $stmt->fetchAll();
    }
    
    /**
     * Merge venues with same license number
     */
    private function mergeByLicense($dup, &$stats) {
        $ids = explode(',', $dup['venue_ids']);
        if (count($ids) < 2) return;
        
        // Fetch venues
        $placeholders = implode(',', array_fill(0, count($ids), '?'));
        $stmt = $this->pdo->prepare("SELECT * FROM venues WHERE id IN ($placeholders)");
        $stmt->execute($ids);
        $venues = $stmt->fetchAll();
        
        // Keep first, merge others
        $canonical = $venues[0];
        for ($i = 1; $i < count($venues); $i++) {
            $this->mergeCluster([$canonical, $venues[$i]], $stats);
        }
    }
    
    /**
     * Update confidence scores based on data quality
     */
    private function updateConfidenceScores() {
        // Higher confidence for:
        // - Multiple sources
        // - Government license data
        // - Recent verification
        // - Complete information
        
        $stmt = $this->pdo->query("
            UPDATE venues
            SET confidence_score = LEAST(
                0.50 +
                (CASE WHEN license_number IS NOT NULL THEN 0.20 ELSE 0 END) +
                (CASE WHEN phone IS NOT NULL THEN 0.10 ELSE 0 END) +
                (CASE WHEN website IS NOT NULL THEN 0.10 ELSE 0 END) +
                (CASE WHEN hours IS NOT NULL THEN 0.10 ELSE 0 END) +
                (CASE WHEN rating IS NOT NULL THEN 0.10 ELSE 0 END) -
                (CASE WHEN source IN ('osm', 'overture') THEN 0.10 ELSE 0 END),
                1.0
            )
            WHERE is_active = 1
        ");
        
        $updated = $stmt->rowCount();
        $this->log("Updated confidence scores for $updated venues");
    }
}

// CLI execution
if (php_sapi_name() === 'cli') {
    $pdo = getDatabaseConnection();
    $dedup = new VenueDeduplicator($pdo);
    $stats = $dedup->run();
    
    echo "\n=== Deduplication Complete ===\n";
    echo "Clusters found: {$stats['clusters_found']}\n";
    echo "Venues merged: {$stats['venues_merged']}\n";
    echo "Records updated: {$stats['records_updated']}\n";
}
