# File: test.py (CORRECTED for active, independent auto-blinking)
import socket
import sys

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

# === Wi-Fi Server Setup ===
HOST = '0.0.0.0'
PORT = 5001
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server_socket.bind((HOST, PORT))
server_socket.listen(1)
print(f"✓ Robot Control Server listening on port {PORT}...")
print("✓ System Ready.")

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

                        # If this is an eye command, record it (logic preserved but unused without blinker)
                        if scs_id == 9:
                            left_pos_cmd = pos
                        elif scs_id == 10:
                            right_pos_cmd = pos

                        packetHandler.SyncWritePos(scs_id, pos, 0, speed)

                    # Send all commands from the PC at once
                    packetHandler.groupSyncWrite.txPacket()
                    packetHandler.groupSyncWrite.clearParam()

                except Exception as e:
                    print(f"Command Error: '{command_str}' -> {e}")

except KeyboardInterrupt:
    print("\nShutting down server...")
finally:
    server_socket.close()
    portHandler.closePort()
    print("Server and port closed.")
