import pyaudio
p = pyaudio.PyAudio()

print("\n--- AVAILABLE AUDIO DEVICES ---")
for i in range(p.get_device_count()):
    info = p.get_device_info_by_index(i)
    # Only print devices that have input channels (Microphones)
    if info["maxInputChannels"] > 0:
        print(f"Index {i}: {info['name']} (Max SR: {int(info['defaultSampleRate'])}Hz)")
p.terminate()
