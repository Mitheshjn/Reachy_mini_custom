import sys
import math
sys.path.append("..")
from scservo_sdk import *  # Uses SC Servo SDK library

# =======================================================
# 1. HARDWARE CALIBRATION & CONFIGURATION
# =======================================================
BAUDRATE     = 1000000
DEVICENAME   = 'COM15'     # Change if your COM port is different
MOVING_SPEED = 400

# Your calibrated Middle ('m') position (Z = 148mm from ground)
# We use this as the absolute "Home" anchor for the IK math.
HOME_SC15 = [575, 470, 560, 460, 575, 485] 

# Servo direction multipliers (derived from your t/m/b data)
# Odds (1,3,5) decrease to go up (-1). Evens (2,4,6) increase to go up (1).
DIR_MULT = [-1, 1, -1, 1, -1, 1] 

# SC15 resolution: 1000 steps over 210 degrees
STEPS_PER_DEGREE = 1000 / 210.0  

# =======================================================
# 2. INVERSE KINEMATICS GEOMETRY (From our CAD specs)
# =======================================================
R_B = 62.5      # Base radius (mm)
R_T = 40.0      # Top radius (mm)
HORN_L = 30.0   # Horn length 'A' (mm)
LEG_L = 112.0   # Leg length 'L' (mm)

Z_OFFSET = 33.5 # Height of the servo splines from the ground (mm)
HOME_Z_USER = 148.0 # The user's Z height at the HOME_SC15 position
HOME_Z_MATH = HOME_Z_USER - Z_OFFSET # Kinematic Z height (118.0 mm)

# Angles of the base joints (Beta) and top joints (Gamma) in radians
# Base pairs are 23.4 deg apart. Top pairs are 25.0 deg apart, offset by 60 deg to cross legs.
BASE_ANGLES_DEG = [-11.7, 11.7, 108.3, 131.7, 228.3, 251.7]
TOP_ANGLES_DEG  = [-47.5, 47.5, 72.5,  167.5, 192.5, 287.5]

base_angles = [math.radians(a) for a in BASE_ANGLES_DEG]
top_angles  = [math.radians(a) for a in TOP_ANGLES_DEG]

# Pre-compute Base and Top Joint coordinates [x, y, z]
base_joints = [[R_B * math.cos(a), R_B * math.sin(a), 0] for a in base_angles]
top_joints  = [[R_T * math.cos(a), R_T * math.sin(a), 0] for a in top_angles]

# =======================================================
# 3. KINEMATICS ENGINE
# =======================================================
def get_rotation_matrix(roll, pitch, yaw):
    """ Generates a 3x3 rotation matrix from Roll (X), Pitch (Y), Yaw (Z) """
    r, p, y = math.radians(roll), math.radians(pitch), math.radians(yaw)
    
    Rx = [[1, 0, 0], 
          [0, math.cos(r), -math.sin(r)], 
          [0, math.sin(r), math.cos(r)]]
          
    Ry = [[math.cos(p), 0, math.sin(p)], 
          [0, 1, 0], 
          [-math.sin(p), 0, math.cos(p)]]
          
    Rz = [[math.cos(y), -math.sin(y), 0], 
          [math.sin(y), math.cos(y), 0], 
          [0, 0, 1]]
    
    # Multiply Rz * Ry * Rx
    R = [[sum(a*b for a,b in zip(Rz_row, Ry_col)) for Ry_col in zip(*Ry)] for Rz_row in Rz]
    R = [[sum(a*b for a,b in zip(R_row, Rx_col)) for Rx_col in zip(*Rx)] for R_row in R]
    return R

def calculate_ik(x, y, z, roll, pitch, yaw):
    """ Returns a list of 6 servo horn angles (in degrees) for a given pose """
    # Adjust Z from ground level to kinematic level
    z_kin = z - Z_OFFSET
    
    R = get_rotation_matrix(roll, pitch, yaw)
    T = [x, y, z_kin]
    
    alphas = []
    
    for i in range(6):
        # 1. Rotate and translate the top joint
        p_x, p_y, p_z = top_joints[i]
        q_x = T[0] + R[0][0]*p_x + R[0][1]*p_y + R[0][2]*p_z
        q_y = T[1] + R[1][0]*p_x + R[1][1]*p_y + R[1][2]*p_z
        q_z = T[2] + R[2][0]*p_x + R[2][1]*p_y + R[2][2]*p_z
        
        # 2. Find vector from base joint to new top joint
        b_x, b_y, b_z = base_joints[i]
        dx = q_x - b_x
        dy = q_y - b_y
        dz = q_z - b_z
        
        # 3. Solve for horn angle (alpha) using trigonometry
        beta = base_angles[i]
        E = 2 * HORN_L * dz
        F = 2 * HORN_L * (dx * math.cos(beta) + dy * math.sin(beta))
        G = dx**2 + dy**2 + dz**2 + HORN_L**2 - LEG_L**2
        
        # Check if position is physically reachable
        if G**2 > E**2 + F**2:
            raise ValueError(f"Position unreachable for Leg {i+1}")
            
        # Standard knee-out solver
        root = math.sqrt(E**2 + F**2 - G**2)
        alpha_rad_1 = 2 * math.atan((E - root) / (F + G))
        alpha_rad_2 = 2 * math.atan((E + root) / (F + G))
        
        # Pick the solution closest to horizontal (0)
        alpha_rad = alpha_rad_1 if abs(alpha_rad_1) < abs(alpha_rad_2) else alpha_rad_2
        alphas.append(math.degrees(alpha_rad))
        
    return alphas

# Pre-calculate the theoretical horn angles at your 'm' (Home) position
try:
    HOME_ALPHAS = calculate_ik(0, 0, HOME_Z_USER, 0, 0, 0)
except ValueError:
    print("FATAL: Home position math is unreachable. Check CAD measurements.")
    quit()

# =======================================================
# 4. MAIN PROGRAM & COMMUNICATION
# =======================================================
portHandler = PortHandler(DEVICENAME)
packetHandler = scscl(portHandler)

if not portHandler.openPort() or not portHandler.setBaudRate(BAUDRATE):
    print("Failed to open port. Check connection.")
    quit()
print("Connection successful! IK Engine Ready.")

try:
    while True:
        print("\n-----------------------------------------------------")
        print("Enter target: X, Y, Z, Roll, Pitch, Yaw (space separated)")
        print("Example: 0 0 148 10 -5 0   (Type 'q' to quit)")
        print(f"(Safe Z range approx: 130 to 175)")
        user_input = input("Target: ").lower()

        if user_input == 'q': break
        
        try:
            # Parse user input
            vals = [float(v) for v in user_input.split()]
            if len(vals) != 6:
                print("Error: Please enter exactly 6 numbers.")
                continue
            t_x, t_y, t_z, t_r, t_p, t_yaw = vals
            
            # 1. Calculate the required theoretical angles for this target
            target_alphas = calculate_ik(t_x, t_y, t_z, t_r, t_p, t_yaw)
            
            # 2. Map theoretical angles to SC15 steps using your HOME calibration
            for i in range(6):
                scs_id = i + 1
                
                # Difference between the angle we need and the angle at Home
                delta_angle = target_alphas[i] - HOME_ALPHAS[i]
                
                # Apply change to the calibrated home SC15 position
                step_change = delta_angle * STEPS_PER_DEGREE * DIR_MULT[i]
                target_pos = int(HOME_SC15[i] + step_change)
                
                # Safety Limit (Prevent servos from destroying the hardware)
                target_pos = max(100, min(900, target_pos)) 
                
                # Add to sync payload
                success = packetHandler.SyncWritePos(scs_id, target_pos, 0, MOVING_SPEED)
                if not success:
                    print(f"[ID:{scs_id}] Failed to add to sync payload")

            # 3. Execute movement
            scs_comm_result = packetHandler.groupSyncWrite.txPacket()
            if scs_comm_result != COMM_SUCCESS:
                print(packetHandler.getTxRxResult(scs_comm_result))
            else:
                print(f">>> Moving to: X={t_x} Y={t_y} Z={t_z} R={t_r} P={t_p} Y={t_yaw}")

            packetHandler.groupSyncWrite.clearParam()
            
        except ValueError as e:
            if "unreachable" in str(e).lower():
                print(f"KINEMATICS ERROR: {e}. The legs cannot physically stretch that far!")
            else:
                print("Input error. Enter digits separated by spaces.")
                
except KeyboardInterrupt:
    print("\nInterrupted by user.")

portHandler.closePort()
print("Port closed. Exited safely.")