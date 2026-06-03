import math
import socket
import tkinter as tk
from tkinter import ttk

# =======================================================
# 1. NETWORK CONFIGURATION (Points to your Pi)
# =======================================================
PI_IP = "192.168.29.247"  # <--- CHANGE THIS TO YOUR PI'S IP ADDRESS
PORT = 5001

# Connect to the Pi
try:
    print(f"Connecting to Pi at {PI_IP}:{PORT}...")
    pi_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    pi_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    pi_socket.connect((PI_IP, PORT))
    print("Connected successfully!")
except Exception as e:
    print(f"Failed to connect to Pi: {e}")
    print("Are you sure the pi_motor_server.py is running on the Pi?")
    quit()

# =======================================================
# 2. INVERSE KINEMATICS CONFIGURATION
# =======================================================
HOME_SC15 = [575, 470, 560, 460, 575, 485] 
DIR_MULT = [-1, 1, -1, 1, -1, 1] 
STEPS_PER_DEGREE = 1000 / 210.0  

R_B = 62.5      
R_T = 40.0      
HORN_L = 30.0   
LEG_L = 112.0   

Z_OFFSET = 33.5 
HOME_Z_USER = 155.0 
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
# 4. TKINTER GUI DASHBOARD
# =======================================================
def send_to_servos(event=None):
    """ Reads slider values, runs IK, and sends string to Pi via Wi-Fi. """
    x = slider_x.get()
    y = slider_y.get()
    z = slider_z.get()
    r = slider_roll.get()
    p = slider_pitch.get()
    yw = slider_yaw.get()
    
    try:
        target_alphas = calculate_ik(x, y, z, r, p, yw)
        final_positions = []
        
        for i in range(6):
            delta_angle = target_alphas[i] - HOME_ALPHAS[i]
            step_change = delta_angle * STEPS_PER_DEGREE * DIR_MULT[i]
            target_pos = int(HOME_SC15[i] + step_change)
            target_pos = max(100, min(900, target_pos)) # Safety constraint
            final_positions.append(str(target_pos))
            
        # Format: "500,450,600,320,500,400\n"
        command = ",".join(final_positions) + "\n"
        pi_socket.sendall(command.encode('utf-8'))
        
        status_label.config(text="Status: OK - Tracking via Wi-Fi", fg="green")
            
    except ValueError:
        status_label.config(text="Status: KINEMATICS LIMIT REACHED!", fg="red")
    except Exception as e:
        status_label.config(text="Status: DISCONNECTED FROM PI!", fg="red")

def reset_home():
    slider_x.set(0)
    slider_y.set(0)
    slider_z.set(HOME_Z_USER)
    slider_roll.set(0)
    slider_pitch.set(0)
    slider_yaw.set(0)
    send_to_servos()

def on_closing():
    try:
        pi_socket.close()
    except:
        pass
    root.destroy()
    print("Exited safely.")

# --- Build the UI Window ---
root = tk.Tk()
root.title("Stewart Platform Controller (Wi-Fi)")
root.geometry("400x500")
root.protocol("WM_DELETE_WINDOW", on_closing)

style = ttk.Style()
style.configure("TScale", thickness=15)

title_label = tk.Label(root, text="6-DOF Wi-Fi Control", font=("Arial", 16, "bold"))
title_label.pack(pady=10)

status_label = tk.Label(root, text="Status: Connected to Pi", font=("Arial", 12), fg="green")
status_label.pack(pady=5)

frame = tk.Frame(root)
frame.pack(pady=10)

def create_slider(parent, label_text, min_val, max_val, default_val):
    row = tk.Frame(parent)
    row.pack(fill='x', padx=20, pady=5)
    tk.Label(row, text=label_text, width=10, anchor='w', font=("Arial", 10, "bold")).pack(side='left')
    slider = tk.Scale(row, from_=min_val, to=max_val, orient='horizontal', 
                      resolution=0.5, length=200, command=send_to_servos)
    slider.set(default_val)
    slider.pack(side='right')
    return slider

slider_x = create_slider(frame, "X (Sway)", -13, 13, 0)
slider_y = create_slider(frame, "Y (Surge)", -13, 13, 0)
slider_z = create_slider(frame, "Z (Heave)", 130, 168, HOME_Z_USER)
slider_roll = create_slider(frame, "Roll", -13, 13, 0)
slider_pitch = create_slider(frame, "Pitch", -20, 20, 0)
slider_yaw = create_slider(frame, "Yaw", -13, 13, 0)

reset_btn = tk.Button(root, text="Reset to Home", font=("Arial", 12, "bold"), 
                      bg="#ff4d4d", fg="white", command=reset_home)
reset_btn.pack(pady=20)

root.mainloop()