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

## 🔌 3. Raspberry Pi (Slave Robot) Setup

The Raspberry Pi interacts directly with the UART serial bus servos and I2S audio hardware.

1. SSH into the Raspberry Pi.
2. Go to pi_code_v5 , Start the robot services:
   ```bash
   ./run.sh
   ```

## 📦 Reference: `pyproject.toml`

For your reference, the included `pyproject.toml` specifies the lock-step dependencies used in v6:

```toml
[project]
name = "reachy-mini-os-v6"
version = "6.0.0"
description = "Fleet-ready Master/Slave OS for Reachy Mini v6"
dependencies = [
    "flask>=3.0.0",
    "flask-sock>=2.0.0",
    "numpy>=1.24.0",
    "opencv-python>=4.8.0",
    "mediapipe>=0.10.0",
    "faster-whisper>=0.10.0",
    "pyaudio>=0.2.13",
    "cryptography>=41.0.0",
    "pyOpenSSL>=23.2.0"
]
```
