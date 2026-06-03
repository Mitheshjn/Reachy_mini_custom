#!/bin/bash
# pi_robot/run.sh

cleanup() {
    echo "Stopping processes..."
    if [ ! -z "$RPICAM_PID" ]; then
        kill "$RPICAM_PID" 2>/dev/null
    fi
    exit 0
}

trap cleanup SIGINT

echo "Starting rpicam..."
# Ensure the camera stream is listening on port 5000
rpicam-vid -t 0 --inline --width 640 --height 480 --framerate 30 --codec h264 --listen -o tcp://0.0.0.0:5000 > /dev/null 2>&1 &
RPICAM_PID=$!

echo "Starting Reachy Mini v2 Hardware Server..."
python robot_server.py

cleanup
