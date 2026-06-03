# File: test.py (CORRECTED for active, independent auto-blinking)
import socket
import sys
import threading
import time
import random

sys.path.append("..")
from scservo_sdk import *

# === Motor UART Setup ===
BAUDRATE = 1000000
DEVICENAME = '/dev/ttyAMA0'
DEFAULT_SPEED = 100
portHandler = PortHandler(DEVICENAME)
packetHandler = scscl(portHandler)
if not (portHandler.openPort() and portHandler.setBaudRate(BAUDRATE)):
    print("FATAL: Failed to open UART port.")
    quit()
print("Motors connected.")

# NEW: Create a lock for the packetHandler to prevent race conditions
# between the main thread (PC commands) and the blinker thread.
motor_lock = threading.Lock()

# === Persistent Auto-Blinker (Now Active) ===
class AutoBlinker(threading.Thread):
    def __init__(self, pkt_handler, lock):
        super().__init__()
        self.daemon = True
        self.pkt_handler = pkt_handler
        self.lock = lock
        self.running = True
        
        # Blink properties
        self.blink_dip = 350
        self.blink_duration = 0.4
        self.min_interval = 10.0
        self.max_interval = 20.0
        
        # State
        self.last_blink_time = time.time()
        # These store the last known "open" positions from the PC
        self.left_eye_open_pos = 190
        self.right_eye_open_pos = 225

        self.start()
        print("✓ Active auto-blinker thread started.")

    def run(self):
        while self.running:
            # Check if it's time to blink AND if the PC has not recently sent an eye command
            is_time_to_blink = time.time() - self.last_blink_time > random.uniform(self.min_interval, self.max_interval)
            can_blink = time.time() - last_eye_command_time > EYE_OVERRIDE_DURATION

            if is_time_to_blink and can_blink:
                self.perform_blink()
                self.last_blink_time = time.time()

            time.sleep(0.1)

    def perform_blink(self):
        """Sends commands directly to the motors to perform a blink."""
        blink_speed = 700
        # --- Close Eyes ---
        with self.lock: # Acquire lock to safely use the packet handler
            self.pkt_handler.SyncWritePos(9, self.left_eye_open_pos + self.blink_dip + 25 , 0, blink_speed)
            self.pkt_handler.SyncWritePos(10, self.right_eye_open_pos + self.blink_dip, 0, blink_speed)
            self.pkt_handler.groupSyncWrite.txPacket()
            self.pkt_handler.groupSyncWrite.clearParam()
        
        time.sleep(self.blink_duration)

        # --- Open Eyes ---
        with self.lock: # Acquire lock again
            self.pkt_handler.SyncWritePos(9, self.left_eye_open_pos, 0, blink_speed)
            self.pkt_handler.SyncWritePos(10, self.right_eye_open_pos, 0, blink_speed)
            self.pkt_handler.groupSyncWrite.txPacket()
            self.pkt_handler.groupSyncWrite.clearParam()

    def update_open_positions(self, left_pos, right_pos):
        """Called by the main thread to keep the blinker aware of the base eye positions."""
        self.left_eye_open_pos = left_pos
        self.right_eye_open_pos = right_pos

    def stop(self):
        self.running = False

# === Global state for overriding blink ===
last_eye_command_time = 0
EYE_OVERRIDE_DURATION = 0.8 # Seconds to pause blinking after a GUI command

# --- Instantiate the blinker, passing it the packet handler and lock ---
auto_blinker = AutoBlinker(packetHandler, motor_lock)

# === Wi-Fi Server Setup ===
HOST = '0.0.0.0'
PORT = 5001
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server_socket.bind((HOST, PORT))
server_socket.listen(1)
print(f"✓ Robot Control Server listening on port {PORT}...")
print("✓ System Ready. Robot is now actively auto-blinking.")

try:
    while True:
        conn, addr = server_socket.accept()
        print(f"✓ Control PC connected from {addr}")

        with conn:
            while True:
                data = conn.recv(1024)
                if not data:
                    print(f"Client {addr} disconnected.")
                    break

                command_str = data.decode('utf-8').strip()

                try:
                    # Acquire lock to ensure PC commands don't clash with blinks
                    with motor_lock:
                        left_pos_cmd, right_pos_cmd = None, None
                        
                        pairs = command_str.split(' ')
                        for pair in pairs:
                            parts = pair.split(',')
                            if len(parts) == 3:
                                scs_id, pos, speed = map(int, parts)
                            elif len(parts) == 2:
                                scs_id, pos = map(int, parts)
                                speed = DEFAULT_SPEED
                            else:
                                continue
                            
                            # If this is an eye command, record it to override blinking
                            if scs_id == 9:
                                left_pos_cmd = pos
                                last_eye_command_time = time.time()
                            elif scs_id == 10:
                                right_pos_cmd = pos
                                last_eye_command_time = time.time()

                            packetHandler.SyncWritePos(scs_id, pos, 0, speed)
                        
                        # Tell the blinker about the new "open" positions
                        if left_pos_cmd is not None and right_pos_cmd is not None:
                            auto_blinker.update_open_positions(left_pos_cmd, right_pos_cmd)

                        # Send all commands from the PC at once
                        packetHandler.groupSyncWrite.txPacket()
                        packetHandler.groupSyncWrite.clearParam()

                except Exception as e:
                    print(f"Command Error: '{command_str}' -> {e}")

except KeyboardInterrupt:
    print("\nShutting down server...")
finally:
    auto_blinker.stop()
    server_socket.close()
    portHandler.closePort()
    print("Server and port closed.")
