import sys
import math
import tkinter as tk
from tkinter import ttk

sys.path.append("..")
from scservo_sdk import *

# =======================================================
# 1. HARDWARE CALIBRATION & CONFIGURATION
# =======================================================
BAUDRATE     = 1000000
DEVICENAME   = 'COM15'
MOVING_SPEED = 400

HOME_SC15 = [575, 470, 560, 460, 575, 485]
DIR_MULT = [-1, 1, -1, 1, -1, 1]
STEPS_PER_DEGREE = 1000 / 210.0

# =======================================================
# 2. INVERSE KINEMATICS GEOMETRY
# =======================================================
R_B = 62.5
R_T = 40.0
HORN_L = 30.0
LEG_L = 112.0

Z_OFFSET = 33.5
HOME_Z_USER = 155.0

BASE_ANGLES_DEG = [-11.7, 11.7, 108.3, 131.7, 228.3, 251.7]
TOP_ANGLES_DEG  = [-12.5, 12.5, 107.5, 132.5, 227.5, 252.5]

# --- NEW CONFIGURATION LINE ---
# Defines which way the horn points for each servo in a tangential setup.
# Odd servos (1,3,5) are on the 'left' of their pair, Even (2,4,6) are on the 'right'.
# We use -1 for left-pointing horns and +1 for right-pointing horns.
TANGENT_DIR = [-1, 1, -1, 1, -1, 1]

base_angles = [math.radians(a) for a in BASE_ANGLES_DEG]
top_angles  = [math.radians(a) for a in TOP_ANGLES_DEG]
base_joints = [[R_B * math.cos(a), R_B * math.sin(a), 0] for a in base_angles]
top_joints  = [[R_T * math.cos(a), R_T * math.sin(a), 0] for a in top_angles]

# =======================================================
# 3. KINEMATICS ENGINE (MODIFIED)
# =======================================================
def get_rotation_matrix(roll, pitch, yaw):
    # This function is correct and does not need changes.
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
        
        # --- THIS IS THE CRITICAL FIX ---
        # OLD RADIAL MATH: F = 2 * HORN_L * (dx * math.cos(beta) + dy * math.sin(beta))
        # NEW TANGENTIAL MATH:
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
# 4. SERVO CONNECTION INITIALIZATION
# =======================================================
# (This section is unchanged)
portHandler = PortHandler(DEVICENAME)
packetHandler = scscl(portHandler)
if not portHandler.openPort() or not portHandler.setBaudRate(BAUDRATE):
    print("Failed to open port. Check connection.")
    quit()
print("Hardware Connected! Starting GUI...")

# =======================================================
# 5. TKINTER GUI DASHBOARD
# =======================================================
# (This entire section is unchanged. Your UI and slider setup is correct.)
def send_to_servos(event=None):
    x, y, z = slider_x.get(), slider_y.get(), slider_z.get()
    r, p, yw = slider_roll.get(), slider_pitch.get(), slider_yaw.get()
    intuitive_pitch, intuitive_roll = -p, -r
    try:
        target_alphas = calculate_ik(x, y, z, intuitive_roll, intuitive_pitch, -yw)
        for i in range(6):
            scs_id = i + 1
            delta_angle = target_alphas[i] - HOME_ALPHAS[i]
            step_change = delta_angle * STEPS_PER_DEGREE * DIR_MULT[i]
            target_pos = int(HOME_SC15[i] + step_change)
            target_pos = max(100, min(900, target_pos))
            packetHandler.SyncWritePos(scs_id, target_pos, 0, MOVING_SPEED)
        scs_comm_result = packetHandler.groupSyncWrite.txPacket()
        packetHandler.groupSyncWrite.clearParam()
        if scs_comm_result == COMM_SUCCESS:
            status_label.config(text="Status: OK - Tracking", fg="green")
    except ValueError:
        status_label.config(text="Status: KINEMATICS LIMIT REACHED!", fg="red")

def reset_home():
    slider_x.set(0)
    slider_y.set(0)
    slider_z.set(HOME_Z_USER)
    slider_roll.set(3)
    slider_pitch.set(0)
    slider_yaw.set(0)
    send_to_servos()

def on_closing():
    portHandler.closePort()
    root.destroy()
    print("Port closed. Exited safely.")

root = tk.Tk()
root.title("Stewart Platform Controller")
root.geometry("400x500")
root.protocol("WM_DELETE_WINDOW", on_closing)
style = ttk.Style()
style.configure("TScale", thickness=15)
title_label = tk.Label(root, text="6-DOF Platform Control", font=("Arial", 16, "bold"))
title_label.pack(pady=10)
status_label = tk.Label(root, text="Status: OK", font=("Arial", 12), fg="green")
status_label.pack(pady=5)
frame = tk.Frame(root)
frame.pack(pady=10)

def create_slider(parent, label_text, min_val, max_val, default_val):
    row = tk.Frame(parent)
    row.pack(fill='x', padx=20, pady=5)
    tk.Label(row, text=label_text, width=10, anchor='w', font=("Arial", 10, "bold")).pack(side='left')
    slider = tk.Scale(row, from_=min_val, to=max_val, orient='horizontal', resolution=0.5, length=200, command=send_to_servos)
    slider.set(default_val)
    slider.pack(side='right')
    return slider

slider_x = create_slider(frame, "X (Sway)", -18, 18, 0)
slider_y = create_slider(frame, "Y (Surge)", -18, 18, 0)
slider_z = create_slider(frame, "Z (Heave)", 133, 167, HOME_Z_USER)
slider_roll = create_slider(frame, "Roll", -20, 23, 3)
slider_pitch = create_slider(frame, "Pitch", -20, 20, 0)
slider_yaw = create_slider(frame, "Yaw", -25, 25, 0)

reset_btn = tk.Button(root, text="Reset to Home", font=("Arial", 12, "bold"), bg="#ff4d4d", fg="white", command=reset_home)
reset_btn.pack(pady=20)
root.mainloop()