#!/bin/bash
# Neutral Eats Augmentation Start Script

cd /var/www/html/minerva
PID_FILE="data/augmentor.pid"

start() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo "Augmentor already running (PID: $PID)"
            exit 0
        fi
    fi
    
    echo "Starting continuous augmentor..."
    nohup python3 continuous_augmentor.py >> data/augmentor.log 2>&1 &
    sleep 2
    
    if [ -f "$PID_FILE" ]; then
        echo "Augmentor started (PID: $(cat $PID_FILE))"
    else
        echo "Failed to start augmentor"
        exit 1
    fi
}

stop() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo "Stopping augmentor (PID: $PID)..."
            kill "$PID"
            rm -f "$PID_FILE"
        else
            echo "Augmentor not running"
            rm -f "$PID_FILE"
        fi
    else
        echo "Augmentor not running"
    fi
}

restart() {
    stop
    sleep 2
    start
}

status() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo "Augmentor running (PID: $PID)"
            exit 0
        fi
    fi
    echo "Augmentor not running"
    exit 1
}

case "${1:-start}" in
    start) start ;;
    stop) stop ;;
    restart) restart ;;
    status) status ;;
    *) echo "Usage: $0 {start|stop|restart|status}"; exit 1 ;;
esac
