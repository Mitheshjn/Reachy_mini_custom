# apps/hand_tracking.py
import time

running = False

def start(sdk):
    global running
    running = True
    sdk.ai_enabled = True
    sdk.ai_mode = "HAND"
    print("🎯 Hand Tracking App Started")
    while running:
        time.sleep(0.5)

def stop(sdk):
    global running
    running = False
    sdk.ai_enabled = False
    print("🛑 Hand Tracking App Stopped")