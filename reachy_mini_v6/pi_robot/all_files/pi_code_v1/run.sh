#!/bin/bash

# Function to handle Ctrl+C
cleanup() {
    echo "Stopping processes..."

    # Kill background rpicam process
    if [ ! -z "$RPICAM_PID" ]; then
        kill "$RPICAM_PID" 2>/dev/null
    fi

    exit 0
}

# Trap Ctrl+C (SIGINT)
trap cleanup SIGINT

echo "Starting rpicam..."
rpicam-vid -t 0 --inline --width 640 --height 480 --framerate 30 --codec h264 --listen -o tcp://0.0.0.0:5000 > /dev/null 2>&1 &

# Save PID of background process
RPICAM_PID=$!

echo "Running Python script..."
python test.py

# If python exits normally, cleanup
cleanup
