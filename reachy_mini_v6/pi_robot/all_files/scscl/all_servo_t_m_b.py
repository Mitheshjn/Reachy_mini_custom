import sys
sys.path.append("..")
from scservo_sdk import *  # Uses SC Servo SDK library

# --- Configuration ---
BAUDRATE     = 1000000
DEVICENAME   = 'COM15'     # Change if your COM port is different
MOVING_SPEED = 400         # Moderate speed for smooth simultaneous movement

# --- Servo Position Data ---
# Storing your manual calibration values for each servo ID
servo_data = {
    1: {'t': 165, 'm': 575, 'b': 740},
    2: {'t': 880, 'm': 470, 'b': 310},
    3: {'t': 140, 'm': 560, 'b': 720},
    4: {'t': 875, 'm': 460, 'b': 290},
    5: {'t': 160, 'm': 575, 'b': 730},
    6: {'t': 900, 'm': 485, 'b': 320}
}

# --- Initialization ---
portHandler = PortHandler(DEVICENAME)
packetHandler = scscl(portHandler)

if not portHandler.openPort() or not portHandler.setBaudRate(BAUDRATE):
    print("Failed to open port or set baudrate. Check connection/COM port.")
    quit()

print("Connection successful! Ready to SyncWrite.")

# --- Main Loop ---
try:
    while True:
        # Prompt user for movement command
        print("\nCommands: 't' = Top | 'm' = Middle | 'b' = Bottom | 'q' = Quit")
        cmd = input("Enter command: ").lower()

        if cmd == 'q':
            break
        elif cmd not in ['t', 'm', 'b']:
            print("Invalid command.")
            continue

        # 1. Package the specific position commands for all 6 servos
        for scs_id in range(1, 7):
            target_pos = servo_data[scs_id][cmd]
            
            # SyncWritePos parameters: ID, Position, Time (0), Speed
            success = packetHandler.SyncWritePos(scs_id, target_pos, 0, MOVING_SPEED)
            if not success:
                print(f"[ID:{scs_id}] Failed to add to sync parameter storage")

        # 2. Transmit the packet (All motors move at the exact same millisecond)
        scs_comm_result = packetHandler.groupSyncWrite.txPacket()
        if scs_comm_result != COMM_SUCCESS:
            print(packetHandler.getTxRxResult(scs_comm_result))
        else:
            state_name = {"t": "TOP", "m": "MIDDLE", "b": "BOTTOM"}
            print(f">>> Moving all servos to {state_name[cmd]} position.")

        # 3. Clear the packet storage for the next command
        packetHandler.groupSyncWrite.clearParam()

except KeyboardInterrupt:
    print("\nInterrupted by user.")

# --- Cleanup ---
portHandler.closePort()
print("Port closed. Exited safely.")