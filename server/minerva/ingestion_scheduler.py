#!/usr/bin/env python3
"""
Neutral Eats Ingestion Scheduler
Runs incremental ingestion respecting free API limits
Designed to run via cron every 15-30 minutes
"""

import subprocess
import json
import os
from datetime import datetime

STATE_FILE = '/var/www/html/minerva/data/ingestion_state.json'
LOG_FILE = '/var/www/html/minerva/data/ingestion.log'

def load_state():
    """Load current ingestion state"""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {
        'last_run': None,
        'cells_completed': 0,
        'total_venues': 0,
        'current_phase': 'central_florida',
        'paused': False
    }

def save_state(state):
    """Save ingestion state"""
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def run_incremental():
    """Run one batch of ingestion"""
    state = load_state()
    
    if state.get('paused'):
        print("Ingestion is paused")
        return
    
    print(f"[{datetime.now()}] Running incremental ingestion...")
    print(f"Phase: {state['current_phase']}, Cells done: {state['cells_completed']}")
    
    # Run the pipeline
    result = subprocess.run(
        ['python3', '/var/www/html/minerva/ingestion_pipeline.py', '--central-fl'],
        capture_output=True,
        text=True
    )
    
    # Update state
    state['last_run'] = datetime.now().isoformat()
    
    # Parse output for venue count
    if result.returncode == 0:
        print("Ingestion completed successfully")
        # Extract added count from log if possible
    else:
        print(f"Error: {result.stderr}")
    
    save_state(state)

if __name__ == "__main__":
    run_incremental()
