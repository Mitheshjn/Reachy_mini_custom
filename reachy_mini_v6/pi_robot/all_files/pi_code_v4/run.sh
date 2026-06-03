#!/bin/bash
# pi_robot/run.sh

cleanup() {
    echo "Stopping processes..."
    # Kills background jobs (like the rpicam loop)
    kill $(jobs -p) 2>/dev/null
    exit 0
}

trap cleanup SIGINT

echo "Starting rpicam auto-restart loop..."
# This loop ensures the video server ALWAYS restarts immediately if the PC disconnects.
(
    while true; do
        rpicam-vid -t 0 --inline --width 640 --height 480 --framerate 30 --codec h264 --listen -o tcp://0.0.0.0:5000 > /dev/null 2>&1
        sleep 0.5
    done
) &

echo "Starting Reachy Mini v4 Hardware Server..."
python robot_server.py

cleanup
