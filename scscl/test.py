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
DEVICENAME   = 'COM15'     # CHANGE THIS IF NEEDED
MOVING_SPEED = 100           # 0 = Max speed (best for real-time slider tracking)

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
HOME_Z_USER = 148.0 
HOME_Z_MATH = HOME_Z_USER - Z_OFFSET 

BASE_ANGLES_DEG = [-11.7, 11.7, 108.3, 131.7, 228.3, 251.7]
TOP_ANGLES_DEG  = [-47.5, 47.5, 72.5,  167.5, 192.5, 287.5]

base_angles = [math.radians(a) for a in BASE_ANGLES_DEG]
top_angles  = [math.radians(a) for a in TOP_ANGLES_DEG]
base_joints = [[R_B * math.cos(a), R_B * math.sin(a), 0] for a in base_angles]
top_joints  = [[R_T * math.cos(a), R_T * math.sin(a), 0] for a in top_angles]

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
        F = 2 * HORN_L * (dx * math.cos(beta) + dy * math.sin(beta))
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
portHandler = PortHandler(DEVICENAME)
packetHandler = scscl(portHandler)

if not portHandler.openPort() or not portHandler.setBaudRate(BAUDRATE):
    print("Failed to open port. Check connection.")
    quit()
print("Hardware Connected! Starting GUI...")

# =======================================================
# 5. TKINTER GUI DASHBOARD
# =======================================================
def send_to_servos(event=None):
    """ Reads slider values and sends them to the servos in real-time. """
    x = slider_x.get()
    y = slider_y.get()
    z = slider_z.get()
    r = slider_roll.get()
    p = slider_pitch.get()
    yw = slider_yaw.get()
    
    try:
        target_alphas = calculate_ik(x, y, z, r, p, yw)
        
        for i in range(6):
            scs_id = i + 1
            delta_angle = target_alphas[i] - HOME_ALPHAS[i]
            step_change = delta_angle * STEPS_PER_DEGREE * DIR_MULT[i]
            target_pos = int(HOME_SC15[i] + step_change)
            target_pos = max(100, min(900, target_pos)) # Safety constraint
            
            packetHandler.SyncWritePos(scs_id, target_pos, 0, MOVING_SPEED)

        scs_comm_result = packetHandler.groupSyncWrite.txPacket()
        packetHandler.groupSyncWrite.clearParam()
        
        if scs_comm_result == COMM_SUCCESS:
            status_label.config(text="Status: OK - Tracking", fg="green")
            
    except ValueError:
        # If the math fails (user dragged slider too far), turn text red and don't send command
        status_label.config(text="Status: KINEMATICS LIMIT REACHED!", fg="red")

def reset_home():
    """ Resets all sliders to 0/Home position """
    slider_x.set(0)
    slider_y.set(0)
    slider_z.set(HOME_Z_USER)
    slider_roll.set(0)
    slider_pitch.set(0)
    slider_yaw.set(0)
    send_to_servos()

def on_closing():
    """ Gracefully shut down servos when window is closed """
    portHandler.closePort()
    root.destroy()
    print("Port closed. Exited safely.")

# --- Build the UI Window ---
root = tk.Tk()
root.title("Stewart Platform Controller")
root.geometry("400x500")
root.protocol("WM_DELETE_WINDOW", on_closing)

# Styling
style = ttk.Style()
style.configure("TScale", thickness=15)

title_label = tk.Label(root, text="6-DOF Platform Control", font=("Arial", 16, "bold"))
title_label.pack(pady=10)

status_label = tk.Label(root, text="Status: OK", font=("Arial", 12), fg="green")
status_label.pack(pady=5)

frame = tk.Frame(root)
frame.pack(pady=10)

# Helper function to create labeled sliders
def create_slider(parent, label_text, min_val, max_val, default_val):
    row = tk.Frame(parent)
    row.pack(fill='x', padx=20, pady=5)
    tk.Label(row, text=label_text, width=10, anchor='w', font=("Arial", 10, "bold")).pack(side='left')
    
    # Notice the command=send_to_servos. This fires every time the slider moves!
    slider = tk.Scale(row, from_=min_val, to=max_val, orient='horizontal', 
                      resolution=0.5, length=200, command=send_to_servos)
    slider.set(default_val)
    slider.pack(side='right')
    return slider

# Create the 6 Sliders (Adjust min/max to your liking!)
slider_x = create_slider(frame, "X (Sway)", -40, 40, 0)
slider_y = create_slider(frame, "Y (Surge)", -40, 40, 0)
slider_z = create_slider(frame, "Z (Heave)", 130, 175, HOME_Z_USER)
slider_roll = create_slider(frame, "Roll", -25, 25, 0)
slider_pitch = create_slider(frame, "Pitch", -25, 25, 0)
slider_yaw = create_slider(frame, "Yaw", -30, 30, 0)

reset_btn = tk.Button(root, text="Reset to Home", font=("Arial", 12, "bold"), 
                      bg="#ff4d4d", fg="white", command=reset_home)
reset_btn.pack(pady=20)

# Run the UI
root.mainloop()