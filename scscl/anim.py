# File: pc_controller_gui.py
# Purpose: Runs on your PC to provide a GUI with live video feed and robot control.
# UI UPDATE: Layout is now wider and less tall to fit smaller screens.

import socket
import threading
import time
import cv2
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import math
import random

# =======================================================
# 1. NETWORK & ROBOT CONFIGURATION
# =======================================================
PI_IP = "192.168.29.247"  
VIDEO_PORT = 5000
MOTOR_PORT = 5001

motor_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    motor_socket.connect((PI_IP, MOTOR_PORT))
    print("Successfully connected to the robot's motor control server.")
except Exception as e:
    print(f"FATAL: Could not connect to motor server at {PI_IP}:{MOTOR_PORT}. Error: {e}")
    exit()

# =======================================================
# 2. INVERSE KINEMATICS GEOMETRY 
# =======================================================
R_B, R_T, HORN_L, LEG_L = 62.5, 40.0, 30.0, 112.0
Z_OFFSET = 33.5           
HOME_Z_USER = 155.0       

BASE_ANGLES_DEG =[-11.7, 11.7, 108.3, 131.7, 228.3, 251.7]
TOP_ANGLES_DEG =[-12.5, 12.5, 107.5, 132.5, 227.5, 252.5]
TANGENT_DIR =[-1, 1, -1, 1, -1, 1]

base_angles =[math.radians(a) for a in BASE_ANGLES_DEG]
top_angles  =[math.radians(a) for a in TOP_ANGLES_DEG]
base_joints = [[R_B * math.cos(a), R_B * math.sin(a), 0] for a in base_angles]
top_joints  = [[R_T * math.cos(a), R_T * math.sin(a), 0] for a in top_angles]

HOME_SC15 =[575, 470, 560, 460, 575, 485]
DIR_MULT =[-1, 1, -1, 1, -1, 1]
STEPS_PER_DEGREE = 1000 / 210.0

# =======================================================
# 3. KINEMATICS ENGINE (No changes here)
# =======================================================
def get_rotation_matrix(roll, pitch, yaw):
    r, p, y = math.radians(roll), math.radians(pitch), math.radians(yaw)
    Rx = [[1, 0, 0],[0, math.cos(r), -math.sin(r)],[0, math.sin(r), math.cos(r)]]
    Ry = [[math.cos(p), 0, math.sin(p)], [0, 1, 0],[-math.sin(p), 0, math.cos(p)]]
    Rz = [[math.cos(y), -math.sin(y), 0], [math.sin(y), math.cos(y), 0],[0, 0, 1]]
    R = [[sum(a*b for a,b in zip(Rz_row, Ry_col)) for Ry_col in zip(*Ry)] for Rz_row in Rz]
    R = [[sum(a*b for a,b in zip(R_row, Rx_col)) for Rx_col in zip(*Rx)] for R_row in R]
    return R

def calculate_ik(x, y, z, roll, pitch, yaw):
    z_kin = z - Z_OFFSET
    R = get_rotation_matrix(roll, pitch, yaw)
    T =[x, y, z_kin]
    alphas =[]
    
    for i in range(6):
        p_x, p_y, p_z = top_joints[i]
        q_x = T[0] + R[0][0]*p_x + R[0][1]*p_y + R[0][2]*p_z
        q_y = T[1] + R[1][0]*p_x + R[1][1]*p_y + R[1][2]*p_z
        q_z = T[2] + R[2][0]*p_x + R[2][1]*p_y + R[2][2]*p_z
        
        b_x, b_y, b_z = base_joints[i]
        dx, dy, dz = q_x - b_x, q_y - b_y, q_z - b_z
        beta = base_angles[i]
        E = 2 * HORN_L * dz
        F = 2 * HORN_L * (dy * math.cos(beta) - dx * math.sin(beta)) * TANGENT_DIR[i]
        G = dx**2 + dy**2 + dz**2 + HORN_L**2 - LEG_L**2
        
        if G**2 > E**2 + F**2: raise ValueError("Unreachable")
            
        root = math.sqrt(E**2 + F**2 - G**2)
        alpha_rad_1 = 2 * math.atan((E - root) / (F + G))
        alpha_rad_2 = 2 * math.atan((E + root) / (F + G))
        
        alpha_rad = alpha_rad_1 if abs(alpha_rad_1) < abs(alpha_rad_2) else alpha_rad_2
        alphas.append(math.degrees(alpha_rad))
        
    return alphas

HOME_ALPHAS = calculate_ik(0, 0, HOME_Z_USER, 0, 0, 0)

# =======================================================
# 4. VIDEO STREAMING THREAD (No changes here)
# =======================================================
class VideoStreamer(threading.Thread):
    def __init__(self, stream_url):
        super().__init__()
        self.stream_url, self.cap, self.latest_frame = stream_url, None, None
        self.running, self.daemon = True, True

    def run(self):
        self.cap = cv2.VideoCapture(self.stream_url, cv2.CAP_FFMPEG)
        while self.running:
            ret, frame = self.cap.read()
            if ret: self.latest_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            time.sleep(0.01)

    def stop(self):
        self.running = False
        if self.cap: self.cap.release()

# =======================================================
# 5. PRE-MADE ANIMATION DICTIONARY (No changes here)
# =======================================================
ANIMATIONS = {
    "Boot Up":[
        ({"X (Sway)": 0, "Y (Surge)": 0, "Z (Heave)": 135, "Roll": 0, "Pitch": 15, "Yaw": 0, "Left Eye": 550, "Right Eye": 570}, 0.1),
        ({"X (Sway)": 0, "Y (Surge)": 0, "Z (Heave)": 150, "Roll": 0, "Pitch": -5, "Yaw": 0, "Left Eye": 500, "Right Eye": 500}, 1.0),
        ({"X (Sway)": 0, "Y (Surge)": 0, "Z (Heave)": 155, "Roll": 0, "Pitch": 0,  "Yaw": 0, "Left Eye": 200, "Right Eye": 225}, 0.5)
    ],
    "Shutdown":[
        ({"X (Sway)": 0, "Y (Surge)": 0, "Z (Heave)": 140, "Roll": 0, "Pitch": 20, "Yaw": 0, "Left Eye": 200, "Right Eye": 225}, 2.0),
        ({"X (Sway)": 0, "Y (Surge)": 0, "Z (Heave)": 135, "Roll": 0, "Pitch": 20, "Yaw": 0, "Left Eye": 550, "Right Eye": 570}, 1.0)
    ],
    "Yes / Nod":[
        ({"Pitch": -15, "Z (Heave)": 160}, 0.3), ({"Pitch": 15, "Z (Heave)": 150}, 0.3),
        ({"Pitch": -10, "Z (Heave)": 155}, 0.3), ({"Pitch": 0, "Z (Heave)": 155}, 0.3)
    ],
    "No / Shake":[
        ({"Yaw": -20}, 0.3), ({"Yaw": 20}, 0.3), ({"Yaw": -15}, 0.3), ({"Yaw": 0}, 0.3)
    ],
    "Curious":[
        ({"Roll": 15, "Pitch": -5, "Left Eye": 700, "Right Eye": 500}, 0.5),
        ({"Roll": 15, "Pitch": -5, "Left Eye": 700, "Right Eye": 500}, 1.5),
        ({"Roll": 0, "Pitch": 0, "Left Eye": 500, "Right Eye": 500}, 0.5)
    ],
     "Bottom left":[
        ({"X (Sway)": 0.0, "Y (Surge)": 0.0, "Z (Heave)": 155.0, "Roll": 0.0, "Pitch": 20.0, "Yaw": -25.0, "Left Eye": 200.0, "Right Eye": 225.0, "Both Eye": 200.0}, 0.7),
        ({"X (Sway)": 0.0, "Y (Surge)": 0.0, "Z (Heave)": 155.0, "Roll": 0.0, "Pitch": 20.0, "Yaw": -25.0, "Left Eye": 200.0, "Right Eye": 225.0, "Both Eye": 200.0}, 1.0),
        ({"X (Sway)": 0.0, "Y (Surge)": 0.0, "Z (Heave)": 155.0, "Roll": 0.0, "Pitch": 0.0, "Yaw": 0.0, "Left Eye": 200.0, "Right Eye": 225.0, "Both Eye": 200.0}, 1.0)
    ]
}

# =======================================================
# 6. TKINTER GUI APPLICATION
# =======================================================
class App:
    def __init__(self, root, video_streamer):
        self.root = root
        self.root.title("Reachy Mini - Control Station")
        self.video_streamer = video_streamer
        self.last_command_time = 0
        self.is_animating = False
        self.idle_mode = False

        # =============================================
        # === NEW UI LAYOUT SECTION (THE ONLY PART THAT CHANGED) ===
        # =============================================
        
        # --- Main Layout Frames ---
        # The video feed remains on the left
        self.video_label = tk.Label(root)
        self.video_label.pack(side="left", padx=10, pady=10, anchor='n')

        # A main container for all control widgets on the right
        main_controls_frame = tk.Frame(root)
        main_controls_frame.pack(side="left", fill="both", expand=True, padx=10, pady=10)

        # Create two columns inside the main controls container
        left_col = tk.Frame(main_controls_frame)
        left_col.pack(side="left", fill="y", padx=5)
        
        right_col = tk.Frame(main_controls_frame)
        right_col.pack(side="left", fill="y", padx=5)

        # --- SLIDERS PANEL (Now in the Left Column) ---
        sliders_frame = tk.LabelFrame(left_col, text="Manual Control")
        sliders_frame.pack(fill="x", pady=5)
        
        self.status_label = tk.Label(sliders_frame, text="Status: OK", fg="green")
        self.status_label.pack(pady=5)

        self.sliders = {}
        sliders_config =[
            ("X (Sway)", -18, 18, 0), ("Y (Surge)", -18, 18, 0),
            ("Z (Heave)", 135, 167, HOME_Z_USER), ("Roll", -20, 20, 0),
            ("Pitch", -20, 20, 0), ("Yaw", -25, 25, 0),
            ("Left Eye", 200, 550, 200),      # <-- Replaced Antenna 1
            ("Right Eye", 225, 575, 225),     # <-- Replaced Antenna 2  
            ("Both Eye", 200, 600, 200)       # <-- NEW: Synchronized eye control
        ]
        
        for label, min_v, max_v, default in sliders_config:
            self.sliders[label] = self.create_slider(sliders_frame, label, min_v, max_v, default)

        tk.Button(sliders_frame, text="Reset to Home", command=self.reset_home).pack(pady=10, fill='x')

        # --- ANIMATIONS & RECORDING PANELS (Now in the Right Column) ---
        anim_frame = tk.LabelFrame(right_col, text="Animations & AI")
        anim_frame.pack(fill="x", pady=5)

        btn_grid = tk.Frame(anim_frame)
        btn_grid.pack(pady=5)
        for i, anim_name in enumerate(ANIMATIONS.keys()):
            col = i % 2
            row = i // 2
            tk.Button(btn_grid, text=anim_name, width=12, 
                    command=lambda n=anim_name: self.play_animation(ANIMATIONS[n])).grid(row=row, column=col, padx=2, pady=2)

        self.idle_btn = tk.Button(anim_frame, text="Idle Mode: OFF", bg="gray", fg="white", command=self.toggle_idle)
        self.idle_btn.pack(pady=10, fill="x")

        rec_frame = tk.LabelFrame(right_col, text="Animation Recording")
        rec_frame.pack(fill="x", pady=5)
        tk.Button(rec_frame, text="Log Current Pose", bg="yellow", command=self.log_pose).pack(pady=10, fill="x")
        
        # --- Start Loops ---
        self.update_video_frame()
        self.idle_loop()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    # (The rest of the class methods are exactly the same as before)
    def create_slider(self, parent, label_text, min_val, max_val, default_val):
        row = tk.Frame(parent)
        row.pack(fill='x', pady=2)
        tk.Label(row, text=label_text, width=10, anchor='w').pack(side='left')
        slider = tk.Scale(row, from_=min_val, to=max_val, orient='horizontal', resolution=0.5, length=180, command=self.schedule_send_command)
        slider.set(default_val)
        slider.pack(side='right')
        return slider

    def schedule_send_command(self, event=None):
        if self.is_animating: return 
        if time.time() - self.last_command_time > 0.05:
            self.send_command()
            self.last_command_time = time.time()

    def send_command(self):
        vals = {name: slider.get() for name, slider in self.sliders.items()}
        try:
            target_alphas = calculate_ik(vals["X (Sway)"], vals["Y (Surge)"], vals["Z (Heave)"], -vals["Roll"], -vals["Pitch"], -vals["Yaw"])
            command_parts =[]
            for i in range(6):
                delta_angle = target_alphas[i] - HOME_ALPHAS[i]
                target_pos = int(HOME_SC15[i] + (delta_angle * STEPS_PER_DEGREE * DIR_MULT[i]))
                command_parts.append(f"{i+1},{max(100, min(900, target_pos))}")
            
            # --- Eye control logic: Both Eyes mode with +25 offset for right eye ---
            eye1_pos = int(vals["Left Eye"])
            eye2_pos = int(vals["Right Eye"])
            both_eye_val = int(vals["Both Eye"])
            
            if both_eye_val != 200:  # Both Eyes mode active
                final_eye1 = both_eye_val
                final_eye2 = both_eye_val + 25  # +25 offset for right eye (ID 10)
            else:  # Individual eye mode
                final_eye1 = eye1_pos
                final_eye2 = eye2_pos
            
            # Clamp to valid servo ranges
            final_eye1 = max(200, min(550, final_eye1))
            final_eye2 = max(225, min(575, final_eye2))
            
            command_parts.append(f"9,{final_eye1}")   # Left Eye (ID 9)
            command_parts.append(f"10,{final_eye2}")  # Right Eye (ID 10)
            
            motor_socket.sendall(" ".join(command_parts).encode('utf-8'))
            self.status_label.config(text="Status: OK", fg="green")
        except ValueError:
            self.status_label.config(text="Status: KINEMATICS LIMIT!", fg="red")

    def reset_home(self):
        self.play_animation([({"X (Sway)": 0, "Y (Surge)": 0, "Z (Heave)": HOME_Z_USER, "Roll": 0, "Pitch": 0, "Yaw": 0, "Left Eye": 200, "Right Eye": 225, "Both Eye": 200}, 1.0)])

    def play_animation(self, sequence):
        if self.is_animating: return
        self.is_animating = True
        threading.Thread(target=self._animate_sequence_thread, args=(sequence,), daemon=True).start()

    def _animate_sequence_thread(self, sequence):
        FPS = 30
        for target_pose, duration in sequence:
            start_pose = {name: slider.get() for name, slider in self.sliders.items()}
            end_pose = {name: target_pose.get(name, start_pose[name]) for name in self.sliders.keys()}
            steps = int(max(1, duration * FPS))
            sleep_time = duration / steps
            for step in range(1, steps + 1):
                progress = step / steps
                current_vals = {name: start_pose[name] + (end_pose[name] - start_pose[name]) * progress for name in self.sliders.keys()}
                self.root.after(0, self._update_sliders_from_thread, current_vals)
                time.sleep(sleep_time)
        self.is_animating = False

    def _update_sliders_from_thread(self, values):
        self.is_animating = False 
        for name, val in values.items():
            self.sliders[name].set(val)
        self.send_command()
        self.is_animating = True

    def toggle_idle(self):
        self.idle_mode = not self.idle_mode
        if self.idle_mode:
            # Idle mode turned ON
            self.idle_btn.config(text="Idle Mode: ON", bg="green")
        else:
            # Idle mode turned OFF - reset to home position
            self.idle_btn.config(text="Idle Mode: OFF", bg="gray")
            self.reset_home()  # <-- Reset to home when disabling idle

    def idle_loop(self):
        if self.idle_mode and not self.is_animating:
            idle_target = {
                "Yaw": random.uniform(-10, 10), "Pitch": random.uniform(-5, 5),
                "Z (Heave)": random.uniform(HOME_Z_USER - 2, HOME_Z_USER + 2),
                "Left Eye": random.uniform(200, 400), "Right Eye": random.uniform(200, 400)
            }
            duration = random.uniform(1.0, 2.5)
            self.play_animation([(idle_target, duration)])
        self.root.after(random.randint(3000, 6000), self.idle_loop)

    def log_pose(self):
        vals = {name: round(slider.get(), 2) for name, slider in self.sliders.items()}
        print("\n--- Copy this into your ANIMATIONS dictionary ---")
        dict_str = ", ".join(f'"{k}": {v}' for k, v in vals.items())
        print(f"({{{dict_str}}}, 1.0),")
        print("-------------------------------------------------\n")

    def update_video_frame(self):
        if self.video_streamer.latest_frame is not None:
            img = Image.fromarray(self.video_streamer.latest_frame)
            imgtk = ImageTk.PhotoImage(image=img)
            self.video_label.imgtk = imgtk
            self.video_label.configure(image=imgtk)
        self.root.after(15, self.update_video_frame)

    def on_closing(self):
        self.video_streamer.stop()
        motor_socket.close()
        self.root.destroy()

# --- Main Execution ---
if __name__ == "__main__":
    stream_url = f"tcp://{PI_IP}:{VIDEO_PORT}"
    video_thread = VideoStreamer(stream_url)
    video_thread.start()

    root = tk.Tk()
    app = App(root, video_thread)
    root.mainloop()