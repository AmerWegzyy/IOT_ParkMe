# Hardware Code Upload Guide

This guide explains which Arduino files to upload to each of the ESP32 microcontrollers in the ParkMe system.

## 1. The Normal ESP Microcontroller (Sensor Node)
**What it is:** The standard ESP32 board (e.g., ESP32 WROOM / DEVKIT V1).
**What it does:** Monitors the ultrasonic parking sensor, reads the battery level, runs the LCD/OLED display, and triggers the camera via ESP-NOW when a car parks.

**Code to Upload:**
Upload the project **`ESP32/ParkMeSensorNode/`**.
- Open `ESP32/ParkMeSensorNode/ParkMeSensorNode.ino` in the Arduino IDE.
- Select your standard ESP32 board in the tools menu (e.g., "DOIT ESP32 DEVKIT V1").
- **Important Configuration:** Before flashing, ensure you configure `SECRETS.h` inside the `ESP32/` directory with your Wi-Fi credentials, backend URL, and the `PARKME_CAMERA_ESPNOW_PEER_MAC` (which must be set to the MAC address of the ESP32-CAM board so it knows where to send the trigger).
- **Calibration:** Upon first boot, leave the spot empty and hold the calibration button to establish the empty-spot baseline distance.

## 2. The ESP32-CAM Microcontroller (Camera Node)
**What it is:** The ESP32 board with the attached camera module (e.g., AI-Thinker ESP32-CAM).
**What it does:** Idles until it receives an instant ESP-NOW trigger from the Sensor Node. Once triggered, it snaps a high-resolution picture of the license plate and uploads it directly to the backend.

**Code to Upload:**
Upload the project **`ESP32/ParkMeCameraNode/`**.
- Open `ESP32/ParkMeCameraNode/ParkMeCameraNode.ino` in the Arduino IDE.
- Select the "AI Thinker ESP32-CAM" board in the Arduino IDE.
- Ensure **PSRAM** is set to **Enabled** in the Arduino IDE tools menu.
- **Important Configuration:** Ensure `SECRETS.h` is properly configured with your Wi-Fi credentials and backend URL.

## 3. Shared Files & Dependencies
Both nodes share the following files during compilation:
- `ESP32/SECRETS.h`: Contains all API keys, Wi-Fi credentials, and hardcoded variables. (Note: You will need to copy `SECRETS.example.h` to `SECRETS.h` and fill it in before compiling).
- `ESP32/ParkMeCommon/`: Contains shared logic for backend response parsing and battery calculations.
- `ESP32/ParkMeLcd/`: Contains the I2C display driver logic used by the Sensor node.

Make sure your Arduino IDE has the necessary libraries installed (e.g., `ArduinoJson`, `HTTPClient`, etc.) to avoid compile errors.
