# Reachy Mini OS v6 - Team Setup Guide

Welcome to the **Reachy Mini OS v6** fleet deployment repository. This version utilizes a decoupled Master-Slave architecture, allowing heavy processing (AI, Computer Vision, Voice) to run on a PC/Laptop (Master) while a lightweight server runs on the Raspberry Pi Zero 2W (Slave).

This repository is optimized for **`uv`**, the ultra-fast Python package installer and resolver. Your team can initialize and run the entire environment in seconds without manually managing complex virtual environments.

---

## Repository Directory Structure

Make sure your shared folder is structured exactly as follows before distributing:

```text
reachy_mini_v6/
├── pi_code_v5/                   # Copy this folder to the Raspberry Pi
│   ├── run.sh                     # Auto-restart camera/server loop
│   ├── robot_server.py            # Pi Hardware I/O listener (Ports 5001-5003)
│
├── pc_server/                     # Run this folder on your PC/Laptop
│   ├── server.py                  # Flask HTTPS Master server (Port 8080)
│   ├── reachy_mini_sdk.py         # Universal SDK & Kinematics engine
│   ├── config.json                # System parameters & Ollama configurations
│   ├── animations.json            # Categorized built-in & custom keyframes
│   ├── pyproject.toml             # uv package declaration file
│   ├── apps/                      # Pluggable applications
│   └── calibrations/              # Holds individual IP-based calibration profiles
│   │   ├── face_tracking.py
│   │   └── hand_tracking.py
│   └── templates/
│       └── index.html             # Fleet Calibration UI
```

---

## 1. Install `uv` (All Platforms)

`uv` replaces `pip`, `venv`, and `conda` with a single binary. It is significantly faster and handles platform-specific wheel compilation automatically.

Open your terminal or PowerShell and run the installation script:

*   **macOS / Linux:**
    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```
*   **Windows (PowerShell):**
    ```powershell
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    ```

Restart your terminal after installation completes to verify by typing `uv --version`.

---

## 2. PC / Laptop (Master Server) Setup

### System Prerequisites
To handle live audio and video streaming, some core system utilities must be available on your PC:

*   **Windows:** Install [FFmpeg](https://ffmpeg.org/download.html) and add it to your system PATH.
*   **macOS:** Install Homebrew dependencies:
    ```bash
    brew install portaudio ffmpeg
    ```
*   **Linux (Ubuntu/Debian):**
    ```bash
    sudo apt update && sudo apt install -y portaudio19-dev python3-pyaudio ffmpeg
    ```

### Dependency Installation & Execution
`uv` uses the `pyproject.toml` file to automatically spin up a virtual environment and run the code with zero manual installation required.

1. Open a terminal in the `pc_server/reachy_mini/reachy_mini_v6` folder.
2. Run the server using:
   ```bash
   uv run server.py
   ```
   or use
   ```bash
   python server.py
   ```

*`uv` will automatically detect the `pyproject.toml` dependencies, create a virtual environment in `.venv`, install the packages (Faster-Whisper, MediaPipe, OpenCV, Flask, etc.), and start the secure HTTPS server.*

---

## 3. Raspberry Pi (Slave Robot) Setup

The Raspberry Pi interacts directly with the UART serial bus servos and I2S audio hardware.

1. SSH into the Raspberry Pi.
2. Go to pi_code_v5 , Start the robot services:
   ```bash
   ./run.sh
   ```
## Connecting to the bot: 

By default when you connect power to the bot it will look for Known wifi devices. If there is no wifi then then it will start its own hotspot with the SSID as reachy mini and the password will be 12345678, you can connect to it and enter the new wifi details. If in any case the bot does not show any hotspot then you 2 options:

Option 1: Use mobile hotspot to connect with the bot. Rename the ssid as " moto e13 " and password as 12345678. This will make bot to connect to your mobile hotspot. Then use any tools/apps like fing (for phone) or ip scanner (for laptop) to get the ip of the robot. Then you need to ssh into the bot, it can be done using terminal / putty etc. In the terminal type 
```
ssh pi-zero@192.168.29.129
```
Here change the ip address according to your robot. Then it will ask for password which is 1234 . Note this is also the password for sudo. Once you logged in type ,
```
cd pi_code_v5
./run.sh
```
This will execute the script in the pi which will accecpt connection from your devices and will stream audio and video to it.
Run the server.py in the pc and open the localhost webpage, in the top right you have the option to enter the ip address of the bot, type the IP address and if connected successfully the robot should come alive. 

If in case the robot is not properly calibrated and is a little off after boot then go to Fleet calibration sub tab in the webapp, and it show some default values in the slider, adjust each individually till its ok , or just click on save and go to the calibration folder in the pc project folder and there will be multiple files with ip address and UUID names. Copy the files save them seperately. Choose a file Copy all the contents in the json file and put it in all the other files. Then restart the server and check. IF it worked then great, if not then use the file content from the other json file and do it again.

For AI chat bot to work, use ollama to run qwen 2 1.5b model locally, if you are using custom ollama port or different model apart from 11434 and qwen 2:1.5b, then in the webapp setting tab change the API url and the model name and you are good to go.

Once the Robot is calibrated, you are done!

## Reference: `pyproject.toml`

For your reference, the included `pyproject.toml` specifies the lock-step dependencies used in v6:

```toml
[project]
name = "reachy-mini-custom"
version = "6.0.0"
description = "Fleet-ready Master/Slave OS for Reachy Mini v6"
readme = "README.md"
requires-python = "==3.11.14"

dependencies = [
    "faster-whisper==1.2.1",
    "flask-sock==0.7.0",
    "mediapipe==0.10.11",
    "opencv-python==4.13.0.92",
    "piper-tts==1.4.1",
    "pyaudio==0.2.14",
    "pyopenssl==26.0.0",
    "speechrecognition==3.16.0",
    "vosk==0.3.45",
    "webrtcvad==2.0.10"
]
```
