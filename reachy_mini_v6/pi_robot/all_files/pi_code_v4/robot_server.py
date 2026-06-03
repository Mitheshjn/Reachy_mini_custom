import socket, sys, threading, time, random, os, io

os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"
import pygame

sys.path.append("..")
from scservo_sdk import *

# === Initialize Pygame (Fixes Popping, keeps I2S awake) ===
try:
    pygame.mixer.init(frequency=22050, size=-16, channels=1, buffer=2048)
except Exception as e:
    print("Pygame audio init failed:", e)

last_active_time = time.time()

# Watchdog: Stops the Pi server ONLY if inactive for 5 minutes (300 seconds)
def watchdog():
    global last_active_time
    while True:
        if time.time() - last_active_time > 300:
            print("No active connection for 5 minutes. Shutting down to save power.")
            os._exit(0)
        time.sleep(10)
threading.Thread(target=watchdog, daemon=True).start()

# === Dedicated Audio Streaming Server (Port 5002) ===
def audio_stream_server():
    global last_active_time
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('0.0.0.0', 5002))
    sock.listen(1)
    print("✓ Audio Stream Server listening on port 5002")

    while True:
        try:
            conn, addr = sock.accept()
            conn.settimeout(2.0)
            with conn:
                while True:
                    try:
                        header = conn.recv(10)
                        if not header: break
                        last_active_time = time.time()
                        
                        size = int(header.decode('utf-8').strip())
                        data = b""
                        while len(data) < size:
                            packet = conn.recv(min(4096, size - len(data)))
                            if not packet: break
                            data += packet
                        
                        # Added seek(0) and try/except to prevent Pygame crash on bad audio
                        try:
                            audio_buffer = io.BytesIO(data)
                            audio_buffer.seek(0)
                            pygame.mixer.music.load(audio_buffer)
                            pygame.mixer.music.play()
                            while pygame.mixer.music.get_busy():
                                time.sleep(0.05)
                        except Exception as e:
                            print(f"Pygame failed to play audio chunk: {e}")
                            
                    except socket.timeout: continue
        except Exception as e:
            print(f"Audio Stream Reset: {e}")

threading.Thread(target=audio_stream_server, daemon=True).start()

# === Motor Setup ===
BAUDRATE = 1000000
DEVICENAME = '/dev/ttyAMA0'
DEFAULT_SPEED = 100
portHandler = PortHandler(DEVICENAME)
packetHandler = scscl(portHandler)
if not (portHandler.openPort() and portHandler.setBaudRate(BAUDRATE)):
    print("FATAL: Failed to open UART port.")
    quit()

motor_lock = threading.Lock()
last_eye_command_time = 0

class AutoBlinker(threading.Thread):
    def __init__(self, pkt_handler, lock):
        super().__init__()
        self.daemon = True
        self.pkt_handler = pkt_handler
        self.lock = lock
        self.running = True
        self.blinking_enabled = True
        self.blink_dip = 350
        self.blink_duration = 0.3
        self.last_blink_time = time.time()
        self.left_eye_open_pos = 190
        self.right_eye_open_pos = 225
        self.start()

    def run(self):
        global last_eye_command_time
        while self.running:
            is_time = time.time() - self.last_blink_time > random.uniform(15.0, 25.0)
            can_blink = time.time() - last_eye_command_time > 0.8
            if is_time and can_blink and self.blinking_enabled:
                self.perform_blink()
                self.last_blink_time = time.time()
            time.sleep(0.1)

    def perform_blink(self):
        speed = 800
        with self.lock:
            self.pkt_handler.SyncWritePos(9, self.left_eye_open_pos + self.blink_dip + 25, 0, speed)
            self.pkt_handler.SyncWritePos(10, self.right_eye_open_pos + self.blink_dip, 0, speed)
            self.pkt_handler.groupSyncWrite.txPacket()
            self.pkt_handler.groupSyncWrite.clearParam()
        time.sleep(self.blink_duration)
        with self.lock:
            self.pkt_handler.SyncWritePos(9, self.left_eye_open_pos, 0, speed)
            self.pkt_handler.SyncWritePos(10, self.right_eye_open_pos, 0, speed)
            self.pkt_handler.groupSyncWrite.txPacket()
            self.pkt_handler.groupSyncWrite.clearParam()

    def update_pos(self, l, r):
        self.left_eye_open_pos, self.right_eye_open_pos = l, r

blinker = AutoBlinker(packetHandler, motor_lock)

# === Motor Command Server (Port 5001) ===
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server_socket.bind(('0.0.0.0', 5001))
server_socket.listen(1)
print(f"✓ Motor Server listening on port 5001")

try:
    while True:
        try:
            conn, addr = server_socket.accept()
            conn.settimeout(2.0)
            with conn:
                while True:
                    try:
                        data = conn.recv(1024)
                        if not data: break
                        last_active_time = time.time()
                        cmds = data.decode('utf-8').strip().split('|')

                        for cmd in cmds:
                            if not cmd: continue
                            if cmd == "BLINK:OFF": blinker.blinking_enabled = False
                            elif cmd == "BLINK:ON": blinker.blinking_enabled = True
                            else:
                                with motor_lock:
                                    pairs = cmd.split(' ')
                                    l_cmd, r_cmd = None, None
                                    for pair in pairs:
                                        parts = pair.split(',')
                                        if len(parts) >= 2:
                                            scs_id, pos = int(parts[0]), int(parts[1])
                                            speed = int(parts[2]) if len(parts)==3 else DEFAULT_SPEED
                                            if scs_id == 9: l_cmd = pos; last_eye_command_time = time.time()
                                            if scs_id == 10: r_cmd = pos; last_eye_command_time = time.time()
                                            packetHandler.SyncWritePos(scs_id, pos, 0, speed)

                                    if l_cmd and r_cmd: blinker.update_pos(l_cmd, r_cmd)
                                    packetHandler.groupSyncWrite.txPacket()
                                    packetHandler.groupSyncWrite.clearParam()
                    except socket.timeout: continue
        except Exception as e:
            print(f"Motor Stream Reset: {e}")

except KeyboardInterrupt: pass
finally:
    blinker.running = False
    server_socket.close()
    portHandler.closePort()
