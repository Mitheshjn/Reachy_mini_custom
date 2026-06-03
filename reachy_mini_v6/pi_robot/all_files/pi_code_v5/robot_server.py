import socket, sys, threading, time, random, os, subprocess

sys.path.append("..")
from scservo_sdk import *

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

# === Audio Streams (ALSA I2S support) ===
def mic_server():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('0.0.0.0', 5002))
    sock.listen(1)
    print("✓ Mic Server listening on 5002")
    while True:
        try:
            conn, _ = sock.accept()
            # Added plughw:0,0 to fix the mic input!
            proc = subprocess.Popen(['arecord', '-D', 'plughw:0,0', '-r', '16000', '-f', 'S16_LE', '-c', '1', '-t', 'raw'], stdout=subprocess.PIPE)
            with conn:
                while True:
                    data = proc.stdout.read(4096)
                    if not data: break
                    conn.sendall(data)
        except Exception as e:
            if 'proc' in locals(): proc.kill()

def speaker_server():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('0.0.0.0', 5003))
    sock.listen(1)
    print("✓ Speaker Server listening on 5003")
    while True:
        try:
            conn, _ = sock.accept()
            with conn:
                while True:
                    header = conn.recv(10)
                    if not header: break
                    size = int(header.decode('utf-8').strip())
                    data = b""
                    while len(data) < size:
                        packet = conn.recv(min(4096, size - len(data)))
                        if not packet: break
                        data += packet
                    
                    with open("/tmp/speak.wav", "wb") as f: f.write(data)
                    # Added plughw:0,0 to fix the speaker output!
                    subprocess.run(["aplay", "-D", "plughw:0,0", "-q", "/tmp/speak.wav"])
        except Exception as e: pass

threading.Thread(target=mic_server, daemon=True).start()
threading.Thread(target=speaker_server, daemon=True).start()

# === Motor Command Server (Port 5001) ===
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server_socket.bind(('0.0.0.0', 5001))
server_socket.listen(1)
print(f"✓ Motor Server listening on port 5001")

try:
    while True:
        try:
            conn, _ = server_socket.accept()
            with conn:
                while True:
                    data = conn.recv(1024)
                    if not data: break
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
        except Exception as e: pass
except KeyboardInterrupt: pass
finally:
    blinker.running = False
    server_socket.close()
    portHandler.closePort()
