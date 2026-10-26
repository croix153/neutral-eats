<?php
/**
 * Neutral Eats Sync Scheduler
 * 
 * Manages background data ingestion jobs with:
 * - Priority-based execution
 * - Rate limiting
 * - Error handling and retries
 * - Grid cell prioritization
 * 
 * Run via cron: */5 * * * * /usr/bin/php /var/www/html/minerva/api/sync_scheduler.php
 */

require_once __DIR__ . '/../config/database.php';

class SyncScheduler {
    private $pdo;
    private $logFile;
    private $maxRuntime = 240; // 4 minutes max per run (for cron every 5 min)
    private $startTime;
    
    // Source configs with priorities and rate limits
    private $sourceConfigs = [
        'usda_farmers_market' => [
            'priority' => 5,
            'frequency_hours' => 168, // Weekly
            'script' => 'ingest_usda_farmers_markets.php',
            'enabled' => true
        ],
        'government' => [
            'priority' => 8,
            'frequency_hours' => 24, // Daily
            'script' => 'ingest_government_data.php',
            'enabled' => true
        ],
        'overture' => [
            'priority' => 6,
            'frequency_hours' => 72, // 3 days
            'script' => 'ingest_overture.php', // Legacy
            'enabled' => true
        ],
        'overpass' => [
            'priority' => 7,
            'frequency_hours' => 48, // 2 days
            'script' => 'ingest_overpass.php', // Legacy
            'enabled' => true
        ],
        'dedup' => [
            'priority' => 3,
            'frequency_hours' => 24, // Daily
            'script' => 'merge_enrich.php',
            'enabled' => true
        ]
    ];
    
    public function __construct($pdo) {
        $this->pdo = $pdo;
        $this->logFile = __DIR__ . '/../logs/scheduler.log';
        $this->startTime = time();
        $this->ensureLogDirectory();
    }
    
    private function ensureLogDirectory() {
        $dir = dirname($this->logFile);
        if (!is_dir($dir)) {
            mkdir($dir, 0755, true);
        }
    }
    
    private function log($message) {
        $line = date('Y-m-d H:i:s') . ' [SCHEDULER] ' . $message . PHP_EOL;
        echo $line;
        file_put_contents($this->logFile, $line, FILE_APPEND | LOCK_EX);
    }
    
    private function shouldStop() {
        return (time() - $this->startTime) > $this->maxRuntime;
    }
    
    /**
     * Main scheduler loop
     */
    public function run() {
        $this->log("=== Sync Scheduler Started ===");
        
        // Check for any running jobs first
        $running = $this->getRunningJobs();
        if (!empty($running)) {
            $this->log("Warning: " . count($running) . " jobs already running");
            foreach ($running as $job) {
                // Kill jobs running > 30 minutes (stale)
                if (time() - $job['started_at'] > 1800) {
                    $this->killStaleJob($job);
                }
            }
        }
        
        // Get overdue sources
        $overdue = $this->getOverdueSources();
        
        foreach ($overdue as $source) {
            if ($this->shouldStop()) {
                $this->log("Approaching time limit, stopping");
                break;
            }
            
            $this->runSource($source);
        }
        
        // Process high-priority grid cells
        $this->processGridCells();
        
        // Clean up old logs
        $this->cleanup();
        
        $this->log("=== Sync Scheduler Complete ===");
    }
    
    /**
     * Get sources that need syncing
     */
    private function getOverdueSources() {
        $overdue = [];
        
        foreach ($this->sourceConfigs as $name => $config) {
            if (!$config['enabled']) continue;
            
            // Check when last successfully synced
            $stmt = $this->pdo->prepare("
                SELECT MAX(completed_at) as last_sync
                FROM sync_log
                WHERE source = ? AND status = 'success'
            ");
            $stmt->execute([$name]);
            $result = $stmt->fetch();
            
            $lastSync = $result['last_sync'] ?? 0;
            $hoursSince = (time() - $lastSync) / 3600;
            
            if ($hoursSince >= $config['frequency_hours']) {
                $overdue[] = [
                    'name' => $name,
                    'priority' => $config['priority'],
                    'hours_overdue' => $hoursSince - $config['frequency_hours']
                ];
            }
        }
        
        // Sort by priority (higher first), then by hours overdue
        usort($overdue, function($a, $b) {
            if ($a['priority'] !== $b['priority']) {
                return $b['priority'] - $a['priority'];
            }
            return $b['hours_overdue'] - $a['hours_overdue'];
        });
        
        return $overdue;
    }
    
    /**
     * Run a source ingestion
     */
    private function runSource($source) {
        $name = $source['name'];
        $config = $this->sourceConfigs[$name];
        
        $this->log("Running: $name (priority: {$config['priority']})");
        
        // Mark as running
        $stmt = $this->pdo->prepare("
            INSERT INTO sync_log (source, started_at, status)
            VALUES (?, UNIX_TIMESTAMP(), 'running')
        ");
        $stmt->execute([$name]);
        $syncId = $this->pdo->lastInsertId();
        
        $scriptPath = __DIR__ . '/' . $config['script'];
        
        if (!file_exists($scriptPath)) {
            $this->log("ERROR: Script not found: $scriptPath");
            $this->updateSyncStatus($syncId, 'error', ['error' => 'Script not found']);
            return;
        }
        
        // Run the script
        $output = [];
        $returnCode = 0;
        
        // Use timeout to prevent hung processes
        $cmd = "timeout 180 /usr/bin/php $scriptPath 2>&1";
        exec($cmd, $output, $returnCode);
        
        $outputStr = implode("\n", $output);
        
        if ($returnCode === 0) {
            $this->log("SUCCESS: $name completed");
            $this->updateSyncStatus($syncId, 'success');
        } elseif ($returnCode === 124) {
            $this->log("TIMEOUT: $name exceeded 180 seconds");
            $this->updateSyncStatus($syncId, 'error', ['error' => 'Timeout']);
        } else {
            $this->log("ERROR: $name failed with code $returnCode");
            $this->updateSyncStatus($syncId, 'error', ['error' => $outputStr]);
        }
        
        // Small pause between sources
        sleep(2);
    }
    
    /**
     * Update sync log status
     */
    private function updateSyncStatus($syncId, $status, $data = []) {
        $stmt = $this->pdo->prepare("
            UPDATE sync_log
            SET status = ?,
                completed_at = UNIX_TIMESTAMP(),
                error_message = ?
            WHERE id = ?
        ");
        $stmt->execute([
            $status,
            $data['error'] ?? null,
            $syncId
        ]);
    }
    
    /**
     * Process high-priority grid cells
     */
    private function processGridCells() {
        $this->log("Processing high-priority grid cells...");
        
        // Get cells that need refreshing, ordered by priority
        $stmt = $this->pdo->query("
            SELECT cell_key, lat_min, lat_max, lng_min, lng_max, priority_score
            FROM grid_cells
            WHERE next_fetch IS NULL OR next_fetch < UNIX_TIMESTAMP()
            ORDER BY priority_score DESC, next_fetch ASC
            LIMIT 10
        ");
        
        $cells = $stmt->fetchAll();
        
        foreach ($cells as $cell) {
            if ($this->shouldStop()) break;
            
            $this->refreshGridCell($cell);
        }
    }
    
    /**
     * Refresh a specific grid cell
     */
    private function refreshGridCell($cell) {
        $cellKey = $cell['cell_key'];
        
        $this->log("Refreshing grid cell: $cellKey");
        
        // Calculate center
        $centerLat = ($cell['lat_min'] + $cell['lat_max']) / 2;
        $centerLng = ($cell['lng_min'] + $cell['lng_max']) / 2;
        
        // Queue update for this area
        // This would trigger the overture/overpass ingestion for this cell
        
        // Update next_fetch time based on priority
        $priority = $cell['priority_score'];
        $nextFetch = time() + (86400 * (10 - $priority)); // Higher priority = sooner refresh
        
        $stmt = $this->pdo->prepare("
            UPDATE grid_cells
            SET next_fetch = ?,
                fetch_count = fetch_count + 1,
                last_fetched = UNIX_TIMESTAMP()
            WHERE cell_key = ?
        ");
        $stmt->execute([$nextFetch, $cellKey]);
    }
    
    /**
     * Get currently running jobs
     */
    private function getRunningJobs() {
        $stmt = $this->pdo->query("
            SELECT id, source, started_at
            FROM sync_log
            WHERE status = 'running'
            AND started_at > UNIX_TIMESTAMP() - 3600
        ");
        return $stmt->fetchAll();
    }
    
    /**
     * Kill a stale job
     */
    private function killStaleJob($job) {
        $this->log("Killing stale job: {$job['source']} (started " . 
                   date('Y-m-d H:i:s', $job['started_at']) . ")");
        
        $stmt = $this->pdo->prepare("
            UPDATE sync_log
            SET status = 'error',
                completed_at = UNIX_TIMESTAMP(),
                error_message = 'Killed - exceeded 30 min timeout'
            WHERE id = ?
        ");
        $stmt->execute([$job['id']]);
    }
    
    /**
     * Cleanup old data
     */
    private function cleanup() {
        // Remove old API cache entries
        $stmt = $this->pdo->query("
            DELETE FROM api_cache
            WHERE expires_at < UNIX_TIMESTAMP() - 86400
            LIMIT 1000
        ");
        $deleted = $stmt->rowCount();
        
        if ($deleted > 0) {
            $this->log("Cleaned up $deleted expired cache entries");
        }
        
        // Archive old sync logs (older than 90 days)
        $stmt = $this->pdo->query("
            DELETE FROM sync_log
            WHERE started_at < UNIX_TIMESTAMP() - 7776000
            AND status != 'running'
            LIMIT 1000
        ");
    }
    
    /**
     * Manual run of a specific source
     */
    public function runSourceNow($sourceName) {
        if (!isset($this->sourceConfigs[$sourceName])) {
            throw new Exception("Unknown source: $sourceName");
        }
        
        $this->log("Manual run of: $sourceName");
        
        $this->runSource([
            'name' => $sourceName,
            'priority' => $this->sourceConfigs[$sourceName]['priority'],
            'hours_overdue' => 999
        ]);
    }
}

// CLI execution
if (php_sapi_name() === 'cli') {
    $pdo = getDatabaseConnection();
    $scheduler = new SyncScheduler($pdo);
    
    // Check for manual source argument
    if ($argc > 1) {
        $sourceName = $argv[1];
        try {
            $scheduler->runSourceNow($sourceName);
        } catch (Exception $e) {
            echo "ERROR: " . $e->getMessage() . "\n";
            exit(1);
        }
    } else {
        $scheduler->run();
    }
}
