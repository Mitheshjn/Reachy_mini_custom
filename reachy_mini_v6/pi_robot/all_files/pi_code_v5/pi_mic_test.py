import socket, subprocess

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind(('0.0.0.0', 5002))
server.listen(1)
print("🎙️ Pi Mic Test Server waiting on port 5002...")

while True:
    conn, addr = server.accept()
    print("PC Connected! Streaming mic audio...")
    
    # -D plughw:0,0 targets your specific Google VoiceHAT card and safely converts 32-bit to 16-bit
    proc = subprocess.Popen(['arecord', '-D', 'plughw:0,0', '-r', '16000', '-f', 'S16_LE', '-c', '1', '-t', 'raw'], stdout=subprocess.PIPE)
    
    try:
        while True:
            data = proc.stdout.read(4096)
            if not data: break
            conn.sendall(data)
    except Exception as e:
        print("Stream ended.")
        proc.kill()
