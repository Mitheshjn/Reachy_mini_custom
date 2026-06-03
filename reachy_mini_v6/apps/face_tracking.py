# apps/face_tracking.py
import time

running = False

def start(sdk):
    global running
    running = True
    sdk.ai_enabled = True
    sdk.ai_mode = "FACE"
    print("🎯 Face Tracking App Started")
    while running:
        time.sleep(0.5)

def stop(sdk):
    global running
    running = False
    sdk.ai_enabled = False
    print("🛑 Face Tracking App Stopped")