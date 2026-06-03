# File: pc_controller_gui.py
# Purpose: Runs on your PC to provide a GUI with live video feed and robot control.
# Updated with tangential horn IK geometry AND EYE Servos (ID 9 & 10)

import socket
import threading
import time
import cv2
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import math

# =======================================================
# 1. NETWORK & ROBOT CONFIGURATION
# =======================================================
PI_IP = "192.168.29.247"  # IMPORTANT: CHANGE THIS TO YOUR PI's IP ADDRESS
VIDEO_PORT = 5000
MOTOR_PORT = 5001

# --- Setup the motor control client socket ---
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

BASE_ANGLES_DEG = [-11.7, 11.7, 108.3, 131.7, 228.3, 251.7]
TOP_ANGLES_DEG = [-12.5, 12.5, 107.5, 132.5, 227.5, 252.5]

TANGENT_DIR = [-1, 1, -1, 1, -1, 1]

# Pre-calculate joint positions in radians
base_angles = [math.radians(a) for a in BASE_ANGLES_DEG]
top_angles  = [math.radians(a) for a in TOP_ANGLES_DEG]
base_joints = [[R_B * math.cos(a), R_B * math.sin(a), 0] for a in base_angles]
top_joints  = [[R_T * math.cos(a), R_T * math.sin(a), 0] for a in top_angles]

# Servo calibration constants
HOME_SC15 = [575, 470, 560, 460, 575, 485]
DIR_MULT = [-1, 1, -1, 1, -1, 1]
STEPS_PER_DEGREE = 1000 / 210.0

# =======================================================
# 3. KINEMATICS ENGINE 
# =======================================================
def get_rotation_matrix(roll, pitch, yaw):
    r, p, y = math.radians(roll), math.radians(pitch), math.radians(yaw)
    Rx = [[1, 0, 0], [0, math.cos(r), -math.sin(r)], [0, math.sin(r), math.cos(r)]]
    Ry = [[math.cos(p), 0, math.sin(p)], [0, 1, 0], [-math.sin(p), 0, math.cos(p)]]
    Rz = [[math.cos(y), -math.sin(y), 0], [math.sin(y), math.cos(y), 0], [0, 0, 1]]
    R = [[sum(a*b for a,b in zip(Rz_row, Ry_col)) for Ry_col in zip(*Ry)] for Rz_row in Rz]
    R = [[sum(a*b for a,b in zip(R_row, Rx_col)) for Rx_col in zip(*Rx)] for R_row in R]
    return R

def calculate_ik(x, y, z, roll, pitch, yaw):
    z_kin = z - Z_OFFSET
    R = get_rotation_matrix(roll, pitch, yaw)
    T = [x, y, z_kin]
    alphas = []
    
    for i in range(6):
        p_x, p_y, p_z = top_joints[i]
        q_x = T[0] + R[0][0]*p_x + R[0][1]*p_y + R[0][2]*p_z
        q_y = T[1] + R[1][0]*p_x + R[1][1]*p_y + R[1][2]*p_z
        q_z = T[2] + R[2][0]*p_x + R[2][1]*p_y + R[2][2]*p_z
        
        b_x, b_y, b_z = base_joints[i]
        dx, dy, dz = q_x - b_x, q_y - b_y, q_z - b_z
        
        beta = base_angles[i]
        E = 2 * HORN_L * dz
        
        # Tangential horn math 
        F = 2 * HORN_L * (dy * math.cos(beta) - dx * math.sin(beta)) * TANGENT_DIR[i]
        G = dx**2 + dy**2 + dz**2 + HORN_L**2 - LEG_L**2
        
        if G**2 > E**2 + F**2:
            raise ValueError("Unreachable")
            
        root = math.sqrt(E**2 + F**2 - G**2)
        alpha_rad_1 = 2 * math.atan((E - root) / (F + G))
        alpha_rad_2 = 2 * math.atan((E + root) / (F + G))
        
        alpha_rad = alpha_rad_1 if abs(alpha_rad_1) < abs(alpha_rad_2) else alpha_rad_2
        alphas.append(math.degrees(alpha_rad))
        
    return alphas

HOME_ALPHAS = calculate_ik(0, 0, HOME_Z_USER, 0, 0, 0)

# =======================================================
# 4. VIDEO STREAMING THREAD
# =======================================================
class VideoStreamer(threading.Thread):
    def __init__(self, stream_url):
        super().__init__()
        self.stream_url = stream_url
        self.cap = None
        self.latest_frame = None
        self.running = True
        self.daemon = True

    def run(self):
        print(f"Connecting to video stream at {self.stream_url}...")
        self.cap = cv2.VideoCapture(self.stream_url, cv2.CAP_FFMPEG)
        if not self.cap.isOpened():
            print("Error: Could not open video stream.")
            return

        while self.running:
            ret, frame = self.cap.read()
            if ret:
                self.latest_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            time.sleep(0.01)

    def stop(self):
        self.running = False
        if self.cap:
            self.cap.release()

# =======================================================
# 5. TKINTER GUI APPLICATION
# =======================================================
class App:
    def __init__(self, root, video_streamer):
        self.root = root
        self.root.title("Stewart Platform")
        self.video_streamer = video_streamer
        self.last_command_time = 0

        # --- Video Panel ---
        self.video_label = tk.Label(root)
        self.video_label.pack(side="left", padx=10, pady=10)

        # --- Control Panel ---
        control_frame = tk.Frame(root)
        control_frame.pack(side="right", padx=10, pady=10, fill="y")
        
        self.status_label = tk.Label(control_frame, text="Status: OK", fg="green")
        self.status_label.pack(pady=5)

        self.sliders = {}
        # We add a 5th value to the tuple for resolution
        sliders_config =[
            ("X (Sway)", -18, 18, 0, 0.5), 
            ("Y (Surge)", -18, 18, 0, 0.5),
            ("Z (Heave)", 135, 167, HOME_Z_USER, 0.5), 
            ("Roll", -20, 20, 0, 0.5),
            ("Pitch", -20, 20, 0, 0.5), 
            ("Yaw", -25, 25, 0, 0.5),
            ("Left Eye", 200, 550, 200, 100.0),   # <-- NEW EYE SLIDER
            ("Right Eye", 225, 575, 225, 100.0),   # <-- NEW EYE SLIDER
            ("Both Eye", 200, 600, 200, 10.0)
        ]
        
        # The loop now unpacks the 5th value and passes it to create_slider
        for label, min_v, max_v, default, res in sliders_config:
            self.sliders[label] = self.create_slider(control_frame, label, min_v, max_v, default, res)

        reset_btn = tk.Button(control_frame, text="Reset to Home", command=self.reset_home)
        reset_btn.pack(pady=20)
        
        self.update_video_frame()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def create_slider(self, parent, label_text, min_val, max_val, default_val, res=0.5):
        row = tk.Frame(parent)
        row.pack(fill='x', pady=2)
        tk.Label(row, text=label_text, width=10, anchor='w').pack(side='left')
        # The resolution is now a variable passed into the function
        slider = tk.Scale(row, from_=min_val, to=max_val, orient='horizontal', 
                          resolution=res, length=150, command=self.schedule_send_command)
        slider.set(default_val)
        slider.pack(side='right')
        return slider

    def schedule_send_command(self, event=None):
        if time.time() - self.last_command_time > 0.05:
            self.send_command()
            self.last_command_time = time.time()

    def send_command(self):
        # 1. Gather Platform IK Slider values
        x = self.sliders["X (Sway)"].get()
        y = self.sliders["Y (Surge)"].get()
        z = self.sliders["Z (Heave)"].get()
        roll = -self.sliders["Roll"].get()  
        pitch = -self.sliders["Pitch"].get()
        yaw = -self.sliders["Yaw"].get()
        
        # 2. Gather eye raw values
                # 2. Gather eye raw values
        eye1_pos = int(self.sliders["Left Eye"].get())
        eye2_pos = int(self.sliders["Right Eye"].get())
        both_eye_val = int(self.sliders["Both Eye"].get())
        
        try:
            # Calculate IK for legs 1-6
            target_alphas = calculate_ik(x, y, z, roll, pitch, yaw)
            command_parts = []
            
            for i in range(6):
                delta_angle = target_alphas[i] - HOME_ALPHAS[i]
                step_change = delta_angle * STEPS_PER_DEGREE * DIR_MULT[i]
                target_pos = int(HOME_SC15[i] + step_change)
                target_pos = max(100, min(900, target_pos))
                command_parts.append(f"{i+1},{target_pos}")
            
            # --- Eye control logic: Both Eyes mode with +25 offset for right eye ---
            # If "Both Eye" slider is not at default (200), use it to control both eyes
            if both_eye_val != 200:
                final_eye1 = both_eye_val          # Left Eye (ID 9)
                final_eye2 = both_eye_val + 25     # Right Eye (ID 10) with +25 offset
            else:
                # Otherwise use individual eye slider values
                final_eye1 = eye1_pos
                final_eye2 = eye2_pos
            
            # Clamp values to valid servo ranges
            final_eye1 = max(200, min(550, final_eye1))
            final_eye2 = max(225, min(575, final_eye2))  # Right eye min per slider config
            
            command_parts.append(f"9,{final_eye1}")
            command_parts.append(f"10,{final_eye2}")
            
            # Join everything into a single string: "1,450 2,560 ... 9,500 10,500"
            command_str = " ".join(command_parts)
            
            motor_socket.sendall(command_str.encode('utf-8'))
            self.status_label.config(text="Status: OK", fg="green")
            
        except ValueError:
            self.status_label.config(text="Status: KINEMATICS LIMIT!", fg="red")
        except Exception as e:
            print(f"Socket send error: {e}")
            self.status_label.config(text="Status: CONNECTION LOST!", fg="red")

    def reset_home(self):
        # Reset platform sliders
        self.sliders["X (Sway)"].set(0)
        self.sliders["Y (Surge)"].set(0)
        self.sliders["Z (Heave)"].set(HOME_Z_USER)
        self.sliders["Roll"].set(0)    
        self.sliders["Pitch"].set(0)
        self.sliders["Yaw"].set(0)
        
        # --- NEW: Reset eye sliders ---
        self.sliders["Left Eye"].set(200)
        self.sliders["Right Eye"].set(225)
        self.sliders["Both Eye"].set(200)
        
        self.send_command()

    def update_video_frame(self):
        if self.video_streamer.latest_frame is not None:
            img = Image.fromarray(self.video_streamer.latest_frame)
            imgtk = ImageTk.PhotoImage(image=img)
            self.video_label.imgtk = imgtk
            self.video_label.configure(image=imgtk)
        self.root.after(15, self.update_video_frame)

    def on_closing(self):
        print("Closing application...")
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