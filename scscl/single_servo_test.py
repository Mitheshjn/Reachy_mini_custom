import sys
sys.path.append("..")
from scservo_sdk import *  # Uses SC Servo SDK library

# --- Configuration ---
SCS_ID       = 8           # Your SC Servo ID
BAUDRATE     = 1000000      # Default SC15 baudrate
DEVICENAME   = 'COM15'      # Windows: 'COM15' | Linux/Pi: '/dev/ttyUSB0'
MOVING_SPEED = 200         # Servo moving speed (0-32767)

# --- Initialization ---
portHandler = PortHandler(DEVICENAME)
packetHandler = scscl(portHandler)

# Open port and set Baudrate
if not portHandler.openPort() or not portHandler.setBaudRate(BAUDRATE):
    print("Failed to open port or set baudrate. Check your DEVICENAME and connections.")
    quit()

print("Connection successful! Servo is ready.")

# --- Main Control Loop ---
try:
    while True:
        # Ask user for a target position
        val = input("Enter position (0 to 1000) or 'q' to quit: ")
        
        if val.lower() == 'q':
            break
            
        try:
            position = int(val)
            # Ensure the value is within the safe SC15 range
            if 0 <= position <= 1000:
                # WritePos parameters: ID, Position, Time (0 = use speed), Speed
                scs_comm_result, scs_error = packetHandler.WritePos(SCS_ID, position, 0, MOVING_SPEED)
                
                # Check for hardware/communication errors
                if scs_comm_result != COMM_SUCCESS:
                    print(packetHandler.getTxRxResult(scs_comm_result))
                elif scs_error != 0:
                    print(packetHandler.getRxPacketError(scs_error))
                else:
                    print(f"Moved servo {SCS_ID} to {position}")
            else:
                print("Error: Position must be between 0 and 1000.")
        except ValueError:
            print("Invalid input. Please enter a valid number.")

except KeyboardInterrupt:
    print("\nProgram interrupted by user.")

# --- Cleanup ---
portHandler.closePort()
print("Port closed. Exited safely.")