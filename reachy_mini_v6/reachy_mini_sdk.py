import socket, threading, time, json, cv2, os, subprocess, urllib.request, re, math, random, queue, wave, io, shutil
import importlib.util
import numpy as np
import mediapipe as mp

class ReachySDK:
    def __init__(self):
        self.pi_ip = ""
        self.current_hwid = ""
        self.cmd_sock = self.mic_sock = self.speaker_sock = None
        self.video_active = True 
        self.cap = None
        self.running_apps = {}
        
        # Sane fallbacks - will be fully overwritten once profile is loaded
        self.pose = {"x": 0.0, "y": 0.0, "z": 148.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0, "base": 500, "left_eye": 200, "right_eye": 225}
        self.is_thinking = self.is_talking = self.talking_thread_active = False
        
        # Continuous Conversation Session States
        self.last_interaction_time = 0.0
        self.conversation_timeout = 10.0  # Time in seconds user has to respond without wake word
        
        self.audio_rx_queue = queue.Queue()
        self.audio_queue = queue.Queue()
        threading.Thread(target=self._audio_worker, daemon=True).start()

        if not os.path.exists("calibrations"): os.makedirs("calibrations")
        self.cal = self._get_default_calibration()

        # IK Physical Constants
        self.R_B, self.R_T, self.HORN_L, self.LEG_L = 62.5, 40.0, 30.0, 112.0
        self.STEPS_PER_DEG = 1000 / 210.0
        self.BASE_ANGLES = [math.radians(a) for a in[-11.7, 11.7, 108.3, 131.7, 228.3, 251.7]]
        self.TOP_ANGLES = [math.radians(a) for a in[-12.5, 12.5, 107.5, 132.5, 227.5, 252.5]]
        self.B_JOINTS = [[self.R_B * math.cos(a), self.R_B * math.sin(a), 0] for a in self.BASE_ANGLES]
        self.T_JOINTS = [[self.R_T * math.cos(a), self.R_T * math.sin(a), 0] for a in self.TOP_ANGLES]
        self.HOME_ALPHAS = self._calc_ik(0, 0, self.cal.get("HOME_Z", 148.0), 0, 0, 0, raw=True)

        print("⏳ Loading Faster-Whisper AI Model...")
        from faster_whisper import WhisperModel
        self.whisper_model = WhisperModel("base.en", device="auto", compute_type="int8")
        
        self.force_listen = False
        self.animations, self.config = {"built_in": {}, "custom": {}}, {}
        self._load_config()
        self._load_animations()

        self._generate_blank_frame("Waiting for Connection...")

        self.ai_enabled = False
        self.ai_mode = "FACE"
        self.mp_face = mp.solutions.face_detection.FaceDetection(min_detection_confidence=0.5)
        self.mp_hands = mp.solutions.hands.Hands(max_num_hands=1, min_detection_confidence=0.5)

        threading.Thread(target=self._vad_stt_worker, daemon=True).start()
        threading.Thread(target=self._esp32_mic_receiver, daemon=True).start()

    def _get_default_calibration(self):
        return {
            "Z_OFFSET": 33.5, "HOME_Z": 148.0,
            "HOME_SC15": [575, 470, 560, 460, 575, 485],
            "DIR_MULT": [-1, 1, -1, 1, -1, 1],
            "TANGENT_DIR": [-1, 1, -1, 1, -1, 1],
            "HOME_BASE": 500, "HOME_L_EYE": 200, "HOME_R_EYE": 225,
            "BLINK_DIP": 350, "BLINK_DURATION": 0.3,
            "LIMITS": {
                "x": [-18, 18], "y": [-18, 18], "z": [130, 167],
                "roll": [-20, 20], "pitch": [-25, 25], "yaw": [-25, 25],
                "base": [0, 1000], "left_eye": [100, 900], "right_eye": [100, 900]
            },
            "INVERT": { "x": 1, "y": 1, "z": 1, "roll": 1, "pitch": 1, "yaw": 1, "base": 1, "left_eye": 1, "right_eye": 1 }
        }

    def connect_and_identify(self, ip):
        self.pi_ip = ip
        try:
            temp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            temp_sock.settimeout(2.0)
            temp_sock.connect((ip, 5001))
            temp_sock.sendall("GET_HWID|".encode('utf-8'))
            response = temp_sock.recv(1024).decode('utf-8')
            temp_sock.close()
            
            match = re.search(r"HWID:([A-Za-z0-9_]+)", response)
            if match:
                hwid = match.group(1)
                self.current_hwid = hwid
                print(f"📡 Identified hardware profile: {hwid}")
                self.load_calibration_by_id(hwid, ip)
                return True
        except Exception as e:
            print(f"⚠️ Could not complete hardware handshake: {e}")
        
        self.load_calibration(ip)
        return False

    def load_calibration_by_id(self, hwid, ip=None):
        self.current_hwid = hwid
        filepath = f"calibrations/{hwid}.json"
        
        if not os.path.exists(filepath) and ip:
            legacy_ip_path = f"calibrations/{ip}.json"
            if os.path.exists(legacy_ip_path):
                print(f"💾 Creating hardware profile from legacy IP layout layout: {legacy_ip_path}")
                shutil.copy(legacy_ip_path, filepath)
        
        self.cal = self._get_default_calibration()
        if os.path.exists(filepath):
            with open(filepath, "r") as f:
                saved = json.load(f)
                for key in saved:
                    if isinstance(saved[key], dict) and key in self.cal:
                        self.cal[key].update(saved[key])
                    else: self.cal[key] = saved[key]
        else:
            self.save_calibration({})
            
        self._update_mapping_store(ip, hwid)
        self._apply_calibration_pose_defaults()

    def _update_mapping_store(self, ip, hwid):
        if not ip or not hwid: return
        map_file = "calibrations/mappings.json"
        mappings = {}
        if os.path.exists(map_file):
            try:
                with open(map_file, "r") as f: mappings = json.load(f)
            except: pass
        mappings[ip] = hwid
        try:
            with open(map_file, "w") as f: json.dump(mappings, f, indent=4)
        except: pass

    def load_calibration(self, ip):
        self.current_hwid = ""
        filepath = f"calibrations/{ip}.json"
        self.cal = self._get_default_calibration()
        if os.path.exists(filepath):
            with open(filepath, "r") as f:
                saved = json.load(f)
                for key in saved:
                    if isinstance(saved[key], dict) and key in self.cal:
                        self.cal[key].update(saved[key])
                    else: self.cal[key] = saved[key]
        self._apply_calibration_pose_defaults()

    def _apply_calibration_pose_defaults(self):
        self.pose = {
            "x": 0.0, "y": 0.0, "z": self.cal.get("HOME_Z", 148.0),
            "roll": 0.0, "pitch": 0.0, "yaw": 0.0,
            "base": self.cal.get("HOME_BASE", 500),
            "left_eye": self.cal.get("HOME_L_EYE", 200),
            "right_eye": self.cal.get("HOME_R_EYE", 225)
        }
        self.HOME_ALPHAS = self._calc_ik(0, 0, self.cal.get("HOME_Z", 148.0), 0, 0, 0, raw=True)

    def save_calibration(self, new_cal_data):
        self.cal.update(new_cal_data)
        filename = self.current_hwid if self.current_hwid else self.pi_ip
        if filename:
            with open(f"calibrations/{filename}.json", "w") as f:
                json.dump(self.cal, f, indent=4)
            self._apply_calibration_pose_defaults()

    def connect(self, ip):
        self.connect_and_identify(ip)

    def connect_sockets(self):
        for s in [self.cmd_sock, self.mic_sock, self.speaker_sock]:
            if s:
                try: s.close()
                except: pass
        try:
            self.cmd_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.cmd_sock.connect((self.pi_ip, 5001))
            self.mic_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.mic_sock.connect((self.pi_ip, 5002))
            self.speaker_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.speaker_sock.connect((self.pi_ip, 5003))

            threading.Thread(target=self._pi_mic_receiver, daemon=True).start()
            threading.Thread(target=self._video_loop, daemon=True).start()
            
            self.go_home()
            self.update_pi_blinker_config()
            self.play_audio("System connected.")
        except Exception as e: print(f"Socket connection error to {self.pi_ip}: {e}")

    def update_pi_blinker_config(self):
        if self.cmd_sock:
            dip = self.cal.get("BLINK_DIP", 350)
            dur = self.cal.get("BLINK_DURATION", 0.3)
            l_open = self.cal.get("HOME_L_EYE", 200)
            r_open = self.cal.get("HOME_R_EYE", 225)
            cmd = f"BLINK_CFG:{dip},{dur},{l_open},{r_open}|"
            try: self.cmd_sock.sendall(cmd.encode('utf-8'))
            except: pass

    def _pi_mic_receiver(self):
        while self.pi_ip:
            try:
                data = self.mic_sock.recv(4096)
                if not data: break
                if self.config.get("mic_source") == "pi": self.audio_rx_queue.put(data)
            except: break

    def _esp32_mic_receiver(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind(('0.0.0.0', 5004))
        server.listen(1)
        while True:
            try:
                conn, _ = server.accept()
                with conn:
                    while True:
                        data = conn.recv(4096)
                        if not data: break
                        if self.config.get("mic_source") == "esp32": self.audio_rx_queue.put(data)
            except: pass

    def execute_voice_command(self, text):
        raw_text = text.lower().strip()
        cleaned_text = re.sub(r'[^\w\s]', '', raw_text)
        
        limits = self.cal.get("LIMITS", {})
        h_z = self.cal.get("HOME_Z", 148.0)
        h_base = self.cal.get("HOME_BASE", 500)
        h_leye = self.cal.get("HOME_L_EYE", 200)
        h_reye = self.cal.get("HOME_R_EYE", 225)
        dip = self.cal.get("BLINK_DIP", 350)

        # 1. Close Eyes
        if any(ph in cleaned_text for ph in ["close eyes", "go to sleep", "sleep now", "shutdown eyes", "close your eyes"]):
            self.play_audio("Resting my optical sensors now.")
            self.move_to(left_eye=h_leye + dip, right_eye=h_reye + dip)
            return True

        # 2. Open Eyes
        if any(ph in cleaned_text for ph in ["open eyes", "wake up", "open your eyes"]):
            self.play_audio("Powering up optics.")
            self.go_home()
            return True

        # 3. Turn Left
        if any(ph in cleaned_text for ph in ["turn left", "look left", "rotate left"]):
            self.play_audio("Rotating left.")
            b_lims = limits.get("base", [0, 1000])
            self.move_to(base=max(b_lims[0], h_base - 180), yaw=-15.0)
            return True

        # 4. Turn Right
        if any(ph in cleaned_text for ph in ["turn right", "look right", "rotate right"]):
            self.play_audio("Rotating right.")
            b_lims = limits.get("base", [0, 1000])
            self.move_to(base=min(b_lims[1], h_base + 180), yaw=15.0)
            return True

        # 5. Look Up
        if any(ph in cleaned_text for ph in ["look up", "tilt up"]):
            self.play_audio("Looking up.")
            p_lims = limits.get("pitch", [-25, 25])
            self.move_to(pitch=max(p_lims[0], -15.0))
            return True

        # 6. Look Down
        if any(ph in cleaned_text for ph in ["look down", "tilt down"]):
            self.play_audio("Looking down.")
            p_lims = limits.get("pitch", [-25, 25])
            self.move_to(pitch=min(p_lims[1], 18.0))
            return True

        # 7. Tilt Left
        if any(ph in cleaned_text for ph in ["tilt left", "lean left"]):
            self.play_audio("Leaning left.")
            r_lims = limits.get("roll", [-20, 20])
            self.move_to(roll=max(r_lims[0], -15.0))
            return True

        # 8. Tilt Right
        if any(ph in cleaned_text for ph in ["tilt right", "lean right"]):
            self.play_audio("Leaning right.")
            r_lims = limits.get("roll", [-20, 20])
            self.move_to(roll=min(r_lims[1], 15.0))
            return True

        # 9. Nod Head
        if any(ph in cleaned_text for ph in ["nod head", "nod your head", "say yes", "agree"]):
            self.play_audio("I agree.")
            self.play_animation("Yes / Nod")
            return True

        # 10. Shake Head
        if any(ph in cleaned_text for ph in ["shake head", "say no", "disagree"]):
            self.play_audio("I do not think so.")
            self.play_animation("No / Shake")
            return True

        # 11. Blink
        if cleaned_text == "blink" or "double blink" in cleaned_text:
            self.play_audio("Blinking.")
            self.toggle_blink(True)
            return True

        # 12. Go Home / Center
        if any(ph in cleaned_text for ph in ["go home", "reset position", "look forward", "center yourself"]):
            self.play_audio("Returning home.")
            self.go_home()
            return True

        # 13. Dance
        if any(ph in cleaned_text for ph in ["dance", "move around", "do a dance"]):
            self.play_audio("Processing rhythm parameters.")
            self.play_animation("Curious")
            return True

        return False

    def _vad_stt_worker(self):
        import pyaudio 
        wake_words = [w.strip() for w in self.config.get("wake_word", "hey baymax").lower().split(",")]
        p = pyaudio.PyAudio()
        try: playback_stream = p.open(format=pyaudio.paInt16, channels=1, rate=16000, output=True)
        except: playback_stream = None

        is_recording, silence_chunks, audio_buffer, SILENCE_THRESHOLD = False, 0, [], 1500  

        def process_audio(audio_array, was_forced):
            try:
                segments, _ = self.whisper_model.transcribe(audio_array.astype(np.float32)/32768.0, beam_size=1)
                text = "".join([segment.text for segment in segments]).lower().strip()
                if text:
                    print(f"✅ [Whisper Heard]: {text}") 
                    in_session = (time.time() - self.last_interaction_time) < self.conversation_timeout
                    found_wake = next((w for w in wake_words if w in text), None)
                    
                    if found_wake or in_session or was_forced:
                        prompt = text.split(found_wake)[1].strip() if (found_wake and found_wake in text) else text
                        if prompt:
                            self.last_interaction_time = time.time()
                            if self.execute_voice_command(prompt):
                                print(f"🎯 Voice command intercepted successfully: {prompt}")
                            else:
                                self.chat_generate(prompt)
            except Exception as e: print("Whisper processing error:", e)

        while True:
            raw_data = self.audio_rx_queue.get()
            if self.is_talking or time.time() < getattr(self, 'echo_block_until', 0):
                is_recording, audio_buffer, silence_chunks = False, [], 0
                while not self.audio_rx_queue.empty(): self.audio_rx_queue.get_nowait()
                continue

            vol = int(self.config.get("mic_volume", 3))
            
            if len(raw_data) % 2 != 0: 
                raw_data = raw_data[:-1]
                
            if len(raw_data) < 2 or vol == 0: continue 
            audio_data = np.clip(np.frombuffer(raw_data, dtype=np.int16) * float(vol), -32768, 32767).astype(np.int16)
            
            if playback_stream:
                try: playback_stream.write(audio_data.tobytes())
                except: pass
            
            rms = np.sqrt(np.mean(audio_data.astype(np.float32)**2))
            if rms > SILENCE_THRESHOLD:
                silence_chunks = 0
                if not is_recording: is_recording, audio_buffer = True, []
            if is_recording:
                audio_buffer.append(audio_data)
                if rms <= SILENCE_THRESHOLD:
                    silence_chunks += 1
                    if silence_chunks > 15:
                        is_recording = False
                        if len(audio_buffer) > 5: 
                            forced = self.force_listen
                            self.force_listen = False 
                            threading.Thread(target=process_audio, args=(np.concatenate(audio_buffer), forced), daemon=True).start()

    def _audio_worker(self):
        while True:
            text = self.audio_queue.get()
            if not text: continue
            safe_text = text.replace('"', '').replace('\n', ' ').strip()
            piper_exe = os.path.join("piper", "piper.exe" if os.name == "nt" else "piper")
            try:
                proc = subprocess.Popen([piper_exe, "--model", os.path.join("piper", self.config.get("piper_model", "en_US-john-medium.onnx")), "--output_raw"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                raw_audio, _ = proc.communicate(input=safe_text.encode('utf-8'))
                
                if self.speaker_sock and len(raw_audio) > 0:
                    spk_vol = float(self.config.get("speaker_volume", 1.0))
                    if spk_vol <= 0.0: continue 
                    curve_vol = spk_vol ** 2.5 
                    
                    try: import audioop; raw_audio = audioop.mul(raw_audio, 2, curve_vol)
                    except: raw_audio = np.clip(np.frombuffer(raw_audio, dtype=np.int16).astype(np.float32) * curve_vol, -32768, 32767).astype(np.int16).tobytes()

                    wav_io = io.BytesIO()
                    with wave.open(wav_io, 'wb') as wav_file:
                        wav_file.setnchannels(1); wav_file.setsampwidth(2); wav_file.setframerate(22050)
                        wav_file.writeframes(raw_audio)
                    
                    self.is_talking = True
                    self.start_talking_loop()
                    self.speaker_sock.sendall(f"{len(wav_io.getvalue()):<10}".encode('utf-8') + wav_io.getvalue())
                    
                    duration = len(raw_audio) / (22050.0 * 2.0)
                    time.sleep(duration)
                    
                    self.is_talking = False
                    self.echo_block_until = time.time() + 0.8
                    self.last_interaction_time = time.time()
            except Exception as e:
                print("Audio generation error:", e)
                self.is_talking = False

    def _calc_ik(self, x, y, z, r, p, yw, raw=False):
        R = self._get_rotation_matrix(r, p, yw)
        T = [x, y, z - self.cal["Z_OFFSET"]]
        alphas =[]
        for i in range(6):
            p_x, p_y, p_z = self.T_JOINTS[i]
            q_x, q_y, q_z = T[0] + R[0][0]*p_x + R[0][1]*p_y + R[0][2]*p_z, T[1] + R[1][0]*p_x + R[1][1]*p_y + R[1][2]*p_z, T[2] + R[2][0]*p_x + R[2][1]*p_y + R[2][2]*p_z
            b_x, b_y, b_z = self.B_JOINTS[i]
            dx, dy, dz = q_x - b_x, q_y - b_y, q_z - b_z
            E, F = 2 * self.HORN_L * dz, 2 * self.HORN_L * (dy * math.cos(self.BASE_ANGLES[i]) - dx * math.sin(self.BASE_ANGLES[i])) * self.cal["TANGENT_DIR"][i]
            G = dx**2 + dy**2 + dz**2 + self.HORN_L**2 - self.LEG_L**2
            if G**2 > E**2 + F**2: return None if not raw else [0]*6
            root = math.sqrt(E**2 + F**2 - G**2)
            a1, a2 = 2 * math.atan((E - root) / (F + G)), 2 * math.atan((E + root) / (F + G))
            alphas.append(math.degrees(a1 if abs(a1) < abs(a2) else a2))
        return alphas

    def _get_rotation_matrix(self, r, p, y):
        r, p, y = map(math.radians, [r, p, y])
        Rx = [[1, 0, 0],[0, math.cos(r), -math.sin(r)],[0, math.sin(r), math.cos(r)]]
        Ry = [[math.cos(p), 0, math.sin(p)], [0, 1, 0],[-math.sin(p), 0, math.cos(p)]]
        Rz = [[math.cos(y), -math.sin(y), 0], [math.sin(y), math.cos(y), 0],[0, 0, 1]]
        return [[sum(a*b for a,b in zip(row, col)) for col in zip(*Rx)] for row in [[sum(a*b for a,b in zip(row, col)) for col in zip(*Ry)] for row in Rz]]

    def go_home(self):
        self.move_to(
            x=0.0, y=0.0, z=self.cal.get("HOME_Z", 148.0),
            roll=0.0, pitch=0.0, yaw=0.0,
            base=self.cal.get("HOME_BASE", 500),
            left_eye=self.cal.get("HOME_L_EYE", 200),
            right_eye=self.cal.get("HOME_R_EYE", 225)
        )

    def move_to(self, speed=150, **kwargs):
        self.pose.update(kwargs)
        p = self.pose.copy()
        
        lims = self.cal.get("LIMITS", self._get_default_calibration()["LIMITS"])
        for axis in ['x', 'y', 'z', 'roll', 'pitch', 'yaw', 'base', 'left_eye', 'right_eye']:
            if axis in p and axis in lims: p[axis] = max(lims[axis][0], min(lims[axis][1], p[axis]))

        inv = self.cal.get("INVERT", self._get_default_calibration()["INVERT"])
        
        dx = p['x']
        dy = p['y'] - 0.0
        dz = p['z'] - self.cal.get("HOME_Z", 148.0)
        droll = p['roll'] - 0.0
        dpitch = p['pitch'] - 0.0
        dyaw = p['yaw']
        dbase = p['base'] - self.cal.get("HOME_BASE", 500)
        dleye = p['left_eye'] - self.cal.get("HOME_L_EYE", 200)
        dreye = p['right_eye'] - self.cal.get("HOME_R_EYE", 225)

        x_logical = dx * inv.get('x', 1)
        y_logical = -3.0 + (dy * inv.get('y', 1))
        z_logical = self.cal.get("HOME_Z", 148.0) + (dz * inv.get('z', 1))
        roll_logical = -1.5 + (droll * inv.get('roll', 1))
        pitch_logical = 9.0 + (dpitch * inv.get('pitch', 1))
        yaw_logical = dyaw * inv.get('yaw', 1)
        
        phys_z = self.cal.get("HOME_Z", 148.0) + (z_logical - self.cal.get("HOME_Z", 148.0))
        
        alphas = self._calc_ik(x_logical, y_logical, phys_z, roll_logical, pitch_logical, yaw_logical)
        if alphas is None: return False

        cmds = []
        for i in range(6):
            pos = int(self.cal["HOME_SC15"][i] + ((alphas[i] - self.HOME_ALPHAS[i]) * self.STEPS_PER_DEG * self.cal["DIR_MULT"][i]))
            cmds.append(f"{i+1},{pos},{speed}")

        phys_base = int(self.cal.get("HOME_BASE", 500) + (dbase * inv.get('base', 1)))
        phys_leye = int(self.cal.get("HOME_L_EYE", 200) + (dleye * inv.get('left_eye', 1)))
        phys_reye = int(self.cal.get("HOME_R_EYE", 225) + (dreye * inv.get('right_eye', 1)))

        cmds.extend([f"7,{phys_base},{speed}", f"9,{phys_leye},{speed}", f"10,{phys_reye},{speed}"])
        
        if self.cmd_sock:
            try: self.cmd_sock.sendall((" ".join(cmds) + "|").encode('utf-8'))
            except: pass
        return True

    def direct_servo_move(self, scs_id, pos, speed=150):
        if self.cmd_sock:
            try: self.cmd_sock.sendall((f"{scs_id},{int(pos)},{speed}|").encode('utf-8'))
            except: pass

    def _generate_blank_frame(self, text):
        placeholder = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.putText(placeholder, text, (150, 240), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        _, f = cv2.imencode('.jpg', placeholder)
        self.latest_frame = f.tobytes()

    def toggle_video(self, state):
        self.video_active = state
        if not state: self._generate_blank_frame("Video Hidden")

    def toggle_blink(self, state):
        if self.cmd_sock: self.cmd_sock.sendall(f"BLINK:{'ON' if state else 'OFF'}|".encode('utf-8'))

    def play_audio(self, text):
        if text.strip(): self.audio_queue.put(text)

    def start_talking_loop(self):
        if self.talking_thread_active: return
        self.talking_thread_active = True
        def loop():
            all_talk_anims = [a for a in self.animations.get("built_in", {}).keys() if "talk" in a.lower()] + \
                             [a for a in self.animations.get("custom", {}).keys() if "talk" in a.lower()]
            while self.is_talking:
                anim = random.choice(all_talk_anims) if all_talk_anims else "Yes / Nod"
                if anim:
                    self.play_animation(anim)
                    time.sleep(2.0)
                else: time.sleep(0.5)
            self.go_home()
            self.talking_thread_active = False
        threading.Thread(target=loop, daemon=True).start()

    def chat_generate(self, prompt):
        if not prompt: return ""
        self.play_animation("Curious") 
        self.is_thinking = True
        
        def thinking_timer():
            time.sleep(4.0)
            if self.is_thinking: self.play_animation("Thinking")
        threading.Thread(target=thinking_timer, daemon=True).start()
        
        try:
            data = json.dumps({"model": self.config['ai_model'], "prompt": prompt, "system": self.config.get('system_prompt', ''), "stream": False}).encode('utf-8')
            req = urllib.request.Request(self.config['ai_url'], method="POST", data=data, headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=10) as response:
                reply = json.loads(response.read().decode('utf-8')).get("response", "")
                reply = re.sub(r'[^\w\s.,!?\'"-]', '', reply).strip()
                self.is_thinking = False
                
                lower_reply = reply.lower()
                chosen_anim = None
                
                if any(x in lower_reply for x in ["hello", "hi ", "hey", "greetings"]):
                    chosen_anim = "new boot" if "new boot" in self.animations["built_in"] else "Boot Up"
                elif any(x in lower_reply for x in ["yes", "agree", "correct", "perfect", "ok"]):
                    chosen_anim = "Yes / Nod"
                elif any(x in lower_reply for x in ["no", "never", "disagree", "incorrect", "dont"]):
                    chosen_anim = "No / Shake"
                elif any(x in lower_reply for x in ["why", "how", "wonder", "curious", "think"]):
                    chosen_anim = "Curious"
                elif "left" in lower_reply: chosen_anim = "Left"
                elif "right" in lower_reply: chosen_anim = "Right"
                elif "nod" in lower_reply: chosen_anim = "Yes / Nod"
                else:
                    if random.random() < 0.5:
                        all_gestures = list(self.animations["built_in"].keys()) + list(self.animations["custom"].keys())
                        safe_gestures = [g for g in all_gestures if g not in ["Boot Up", "Shutdown"]]
                        if safe_gestures: chosen_anim = random.choice(safe_gestures)
                
                if chosen_anim:
                    self.play_animation(chosen_anim)

                self.play_audio(reply)
                return reply
        except Exception as e:
            self.is_thinking = False
            self.play_audio("Error connecting to AI.")
            return "Error."

    def get_apps(self): return [f[:-3] for f in os.listdir("apps") if f.endswith('.py') and f != "__init__.py"] if os.path.exists("apps") else []
    
    def toggle_app(self, app_name):
        if app_name in self.running_apps:
            if hasattr(self.running_apps[app_name], 'stop'): self.running_apps[app_name].stop(self)
            del self.running_apps[app_name]
            return False
        path = os.path.join("apps", f"{app_name}.py")
        if os.path.exists(path):
            spec = importlib.util.spec_from_file_location(app_name, path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            self.running_apps[app_name] = mod
            if hasattr(mod, 'start'): threading.Thread(target=mod.start, args=(self,), daemon=True).start()
            return True
        return False

    def _video_loop(self):
        while True:
            if self.video_active and self.pi_ip:
                self.cap = cv2.VideoCapture(f"tcp://{self.pi_ip}:5000", cv2.CAP_FFMPEG)
                while self.cap.isOpened() and self.video_active and self.pi_ip:
                    ret, frame = self.cap.read()
                    if not ret: break 
                    frame = cv2.flip(frame, 0)
                    if self.ai_enabled: frame = self._process_ai(frame)
                    _, f = cv2.imencode('.jpg', frame)
                    self.latest_frame = f.tobytes()
                if self.cap: self.cap.release()
            time.sleep(1)

    def _process_ai(self, frame):
        h, w = frame.shape[:2]
        cx, cy, ox, oy = w//2, h//2, None, None
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        if self.ai_mode == "FACE":
            res = self.mp_face.process(rgb)
            if res.detections:
                b = res.detections[0].location_data.relative_bounding_box
                ox, oy = int((b.xmin + b.width/2)*w), int((b.ymin + b.height/2)*h)
        else:
            res = self.mp_hands.process(rgb)
            if res.multi_hand_landmarks:
                lm = res.multi_hand_landmarks[0].landmark[9]
                ox, oy = int(lm.x*w), int(lm.y*h)
        if ox and oy:
            cv2.circle(frame, (ox, oy), 10, (0, 255, 0), -1)
            err_x, err_y = ox - cx, oy - cy
            if abs(err_y) > 40: self.pose['pitch'] -= (err_y * 0.0015)
            if abs(err_x) > 40: self.pose['yaw'] -= (err_x * 0.0015)
            if self.pose['yaw'] > 15.0: self.pose['base'] += 5.0; self.pose['yaw'] -= 0.8
            elif self.pose['yaw'] < -15.0: self.pose['base'] -= 5.0; self.pose['yaw'] += 0.8
            self.move_to()
        return frame

    def _load_config(self):
        try:
            with open("config.json", "r") as f: self.config.update(json.load(f))
        except: pass
    def save_config(self, nc): self.config.update(nc); open("config.json", "w").write(json.dumps(self.config))
    
    def _load_animations(self):
        try:
            with open("animations.json", "r") as f:
                data = json.load(f)
                if "built_in" in data and "custom" in data:
                    self.animations = data
                else:
                    self.animations = {"built_in": data, "custom": {}}
        except: pass

    def save_animation(self, n, s, cat="custom"):
        if cat not in ["built_in", "custom"]: cat = "custom"
        self.animations[cat][n] = s
        open("animations.json", "w").write(json.dumps(self.animations, indent=4))

    def delete_animation(self, n):
        if n in self.animations["built_in"]: del self.animations["built_in"][n]
        if n in self.animations["custom"]: del self.animations["custom"][n]
        open("animations.json", "w").write(json.dumps(self.animations, indent=4))

    def rename_animation(self, o, n):
        for cat in ["built_in", "custom"]:
            if o in self.animations[cat]:
                self.animations[cat][n] = self.animations[cat].pop(o)
                break
        open("animations.json", "w").write(json.dumps(self.animations, indent=4))

    def play_animation(self, n):
        steps = []
        if n in self.animations["built_in"]: steps = self.animations["built_in"][n]
        elif n in self.animations["custom"]: steps = self.animations["custom"][n]
        if not steps: return
        
        def run_anim():
            for step in steps:
                dur = step.get("duration", 1.0)
                if step.get("audio", ""): self.play_audio(step["audio"])
                self.move_to(
                    speed=800 if step.get("Left Eye",0) > 400 else 100,
                    x=step.get("X (Sway)", self.pose['x']), y=step.get("Y (Surge)", self.pose['y']),
                    z=step.get("Z (Heave)", self.pose['z']), roll=step.get("Roll", self.pose['roll']),
                    pitch=step.get("Pitch", self.pose['pitch']), yaw=step.get("Yaw", self.pose['yaw']),
                    base=step.get("Base", self.pose['base']), left_eye=step.get("Left Eye", self.pose['left_eye']),
                    right_eye=step.get("Right Eye", self.pose['right_eye'])
                )
                time.sleep(dur)
        threading.Thread(target=run_anim, daemon=True).start()