import socket, sys, threading, time, random, os, subprocess
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"
import pygame

sys.path.append("..")
from scservo_sdk import *

# Initialize Audio mixer to keep I2S hardware awake (prevents popping)
try:
    pygame.mixer.init(frequency=24000, size=-16, channels=2, buffer=4096)
except Exception as e:
    print("Pygame audio init failed:", e)

def speak(text):
    """Try high-quality gTTS first, fallback to offline espeak if no internet."""
    try:
        from gtts import gTTS
        tts = gTTS(text=text, lang='en', tld='co.uk')
        tts.save("temp.mp3")
        pygame.mixer.music.load("temp.mp3")
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            time.sleep(0.1)
    except Exception as e:
        print(f"gTTS failed (no internet?), using offline espeak: {e}")
        # Improved offline voice: -v en-us+f3 (female) -s 150 (speed)
        subprocess.Popen(["espeak", "-v", "en-us+f3", "-s", "150", text]).wait()

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

class AutoBlinker(threading.Thread):
    def __init__(self, pkt_handler, lock):
        super().__init__()
        self.daemon = True
        self.pkt_handler = pkt_handler
        self.lock = lock
        self.running = True
        self.blinking_enabled = True
        self.blink_dip = 350
        self.blink_duration = 0.4
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
        speed = 700
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

last_eye_command_time = 0
blinker = AutoBlinker(packetHandler, motor_lock)

# === Server Setup ===
HOST, PORT = '0.0.0.0', 5001
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server_socket.bind((HOST, PORT))
server_socket.listen(1)
print(f"✓ Robot Ready. Listening on port {PORT}")

try:
    while True:
        conn, addr = server_socket.accept()
        with conn:
            while True:
                data = conn.recv(1024)
                if not data: break
                cmds = data.decode('utf-8').strip().split('|')
                
                for cmd in cmds:
                    if not cmd: continue
                    
                    if cmd == "BLINK:OFF": blinker.blinking_enabled = False
                    elif cmd == "BLINK:ON": blinker.blinking_enabled = True
                    elif cmd.startswith("TTS:"):
                        text = cmd.split(":", 1)[1]
                        threading.Thread(target=speak, args=(text,), daemon=True).start()
                    
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

except KeyboardInterrupt: pass
finally:
    blinker.running = False
    server_socket.close()
    portHandler.closePort()
