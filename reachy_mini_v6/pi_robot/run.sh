#!/bin/bash
cleanup() {
    echo "Stopping processes..."
    kill $(jobs -p) 2>/dev/null
    exit 0
}
trap cleanup SIGINT

echo "Starting rpicam auto-restart loop..."
(
    while true; do
        rpicam-vid -t 0 --inline --width 640 --height 480 --framerate 30 --codec h264 --listen -o tcp://0.0.0.0:5000 > /dev/null 2>&1
        sleep 0.5
    done
) &

echo "Starting Reachy Mini v5 Hardware Server..."
python robot_server.py
cleanup