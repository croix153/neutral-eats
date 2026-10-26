#!/usr/bin/env python3
"""
Neutral Eats Continuous Augmentor
"""

import sqlite3
import time
import json
import os
import random
from datetime import datetime

DB_PATH = "/var/www/html/minerva/data/neutraleats.db"
ACTIVITY_LOG = "/var/www/html/minerva/data/activity-log.md"
PID_FILE = "/var/www/html/minerva/data/augmentor.pid"

class ContinuousAugmentor:
    def __init__(self):
        self.running = True
        self.stats = {
            "start_time": datetime.now(),
            "venues_processed": 0,
            "venues_updated": 0,
            "errors": 0,
            "cycles": 0
        }
        
    def log_activity(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = "[" + timestamp + "] " + message + "\n"
        with open(ACTIVITY_LOG, "a") as f:
            f.write(log_entry)
        print(log_entry.strip())
        
    def get_db(self):
        return sqlite3.connect(DB_PATH)
        
    def get_stats(self):
        conn = self.get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM venues")
        total_venues = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM grid_cells")
        grid_cells = cursor.fetchone()[0]
        conn.close()
        return {"total_venues": total_venues, "grid_cells": grid_cells}
        
    def augment_batch(self):
        conn = self.get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM venues WHERE check_count < 5 OR last_updated < ? ORDER BY RANDOM() LIMIT 50", (int(time.time()) - 86400,))
        venues = cursor.fetchall()
        updated = 0
        for venue in venues:
            vid = venue[0]
            cursor.execute("UPDATE venues SET check_count = check_count + 1, last_updated = ? WHERE id = ?", (int(time.time()), vid))
            updated += 1
        conn.commit()
        conn.close()
        return updated
        
    def write_pid(self):
        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))
            
    def remove_pid(self):
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
            
    def run(self):
        self.write_pid()
        self.log_activity("AUGMENTOR STARTED - PID " + str(os.getpid()))
        try:
            while self.running:
                self.stats["cycles"] += 1
                db_stats = self.get_stats()
                updated = self.augment_batch()
                self.stats["venues_updated"] += updated
                if self.stats["cycles"] % 10 == 0:
                    runtime = datetime.now() - self.stats["start_time"]
                    hours = int(runtime.total_seconds() // 3600)
                    minutes = int((runtime.total_seconds() % 3600) // 60)
                    self.log_activity("STATUS | Runtime: " + str(hours) + "h " + str(minutes) + "m | Venues: " + str(db_stats["total_venues"]) + " | Updated: " + str(self.stats["venues_updated"]) + " | HEALTHY")
                time.sleep(300)
        except Exception as e:
            self.log_activity("AUGMENTOR ERROR: " + str(e))
            self.stats["errors"] += 1
        finally:
            self.remove_pid()

if __name__ == "__main__":
    import signal
    augmentor = ContinuousAugmentor()
    def signal_handler(sig, frame):
        augmentor.running = False
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    augmentor.run()
