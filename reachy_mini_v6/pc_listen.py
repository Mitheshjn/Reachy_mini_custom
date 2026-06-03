import socket
import pyaudio

PI_IP = "192.168.29.247" # <--- Change to your Pi's IP address

# Setup PyAudio to play what it receives
p = pyaudio.PyAudio()
stream = p.open(format=pyaudio.paInt16, channels=1, rate=16000, output=True)

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
print(f"Connecting to Pi at {PI_IP}:5002...")
s.connect((PI_IP, 5002))
print("✅ Connected! Make some noise near the Pi, you should hear it on your PC speakers...")

try:
    while True:
        data = s.recv(4096)
        if not data:
            print("Connection closed by Pi.")
            break
        stream.write(data)
except KeyboardInterrupt:
    print("Stopping test.")
finally:
    s.close()
    stream.stop_stream()
    stream.close()
    p.terminate()