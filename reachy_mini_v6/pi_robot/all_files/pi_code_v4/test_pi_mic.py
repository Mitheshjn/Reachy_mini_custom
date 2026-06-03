import socket
import pyaudio

# Audio Settings
CHUNK = 2048
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 48000  # Matches your device's native max SR for direct hw:0,0 access
MIC_INDEX = 0 # Using Index 0: Google voiceHAT SoundCard

print("Initializing Mic on Pi...")
p = pyaudio.PyAudio()

try:
    # Open Mic stream explicitly using Index 0
    stream_in = p.open(format=FORMAT, 
                       channels=CHANNELS, 
                       rate=RATE, 
                       input=True, 
                       input_device_index=MIC_INDEX,
                       frames_per_buffer=CHUNK)
except Exception as e:
    print(f"Failed to open microphone: {e}")
    p.terminate()
    exit()

# Setup Network Server
server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind(('0.0.0.0', 6000))
server.listen(1)

print("Waiting for PC to connect on port 6000...")
conn, addr = server.accept()
print(f"✓ PC Connected from {addr}. Streaming Mic to PC...")

try:
    while True:
        # Read from Pi Mic and send to PC
        data = stream_in.read(CHUNK, exception_on_overflow=False)
        conn.sendall(data)
except KeyboardInterrupt:
    print("\nStopping...")
except Exception as e:
    print(f"\nConnection lost: {e}")
finally:
    conn.close()
    server.close()
    stream_in.stop_stream()
    stream_in.close()
    p.terminate()
