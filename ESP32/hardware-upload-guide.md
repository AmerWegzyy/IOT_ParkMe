# ParkMe Hardware Upload Guide

This guide explains how to properly configure and upload the firmware to the ParkMe microcontrollers.

## 1. Microcontrollers Overview

The ParkMe system uses two different microcontrollers for each parking spot / gate setup:

1. **Sensor Node (`ESP32/ParkMeSensorNode`)**
   - **Hardware**: Standard ESP32 board (e.g., NodeMCU-32S, ESP32 Dev Module).
   - **Purpose**: Handles the ultrasonic distance sensor, the I2C OLED display, and the calibration button. It detects if a spot is free or occupied and updates the screen.
   - **Upload Target**: `ESP32 Dev Module` (or your specific ESP32 variant).

2. **Camera Node (`ESP32/ParkMeCameraNode`)**
   - **Hardware**: ESP32-CAM (AI-Thinker module).
   - **Purpose**: Takes photos of license plates, uploads them to the backend for verification, and controls the gate relay to open/close the barrier.
   - **Upload Target**: `AI Thinker ESP32-CAM`.

---

## 2. Configuring `SECRETS.h`

Before uploading *any* code, you must create a configuration file that holds your WiFi credentials, backend URLs, and device IDs. 

1. Duplicate the `SECRETS.example.h` file in the `ESP32/` directory and name the copy `SECRETS.h`.
2. Open `SECRETS.h` and configure the following essential parameters:

### **Network & Backend**
- `PARKME_WIFI_SSID`: Your local WiFi network or mobile hotspot name.
- `PARKME_WIFI_PASSWORD`: Your WiFi password.
- `PARKME_SERVER_HOST`: The URL of your deployed backend (e.g., `your-parkme-backend.a.run.app` or a local IP if hosting locally).
- `PARKME_SERVER_SCHEME`: Set to `"https"` if using a cloud deployment, or `"http"` if testing locally.

### **Spot Configuration**
- `PARKME_GATE_SPOT_ID`: The exact ID of the parking spot in Firestore (e.g., `"C1"`). This must match the database exactly.
- `PARKME_DISPLAY_ID`: The unique ID for the display (e.g., `"display-c1"`).

### **ESP-NOW MAC Address (Crucial for Camera/Sensor Sync)**
The Sensor Node and Camera Node talk directly to each other using ESP-NOW to reduce latency.
- `PARKME_CAMERA_ESPNOW_PEER_MAC`: You need to find out the MAC address of your **Camera Node** (it's printed to the serial monitor when the camera node boots up). Once you have it, update this value so the Sensor Node knows exactly where to send trigger signals!

---

## 3. How to Upload

### Prerequisites
- Install the **Arduino IDE**.
- Install the **ESP32 Board Manager** (by Espressif) in the Arduino IDE.
- (Optional but recommended) Install `U8g2` library if you want to use the `ScreenProbe` diagnostic tool.

### Uploading to the Sensor Node
1. Connect the standard ESP32 to your computer via USB.
2. Open `ESP32/ParkMeSensorNode/ParkMeSensorNode.ino` in the Arduino IDE.
3. Go to **Tools > Board** and select `ESP32 Dev Module`.
4. Go to **Tools > Port** and select the correct COM port.
5. Click **Upload**.
   - *Note: On some ESP32 boards, you may need to hold the "BOOT" button when the terminal says "Connecting..." to allow the upload to begin.*

### Uploading to the Camera Node
1. Connect the ESP32-CAM to your computer. (Usually requires an FTDI programmer since the board has no built-in USB-to-Serial chip).
   - Ensure `IO0` is connected to `GND` to put the board into flashing mode.
   - Supply it with stable 5V power.
2. Open `ESP32/ParkMeCameraNode/ParkMeCameraNode.ino` in the Arduino IDE.
3. Go to **Tools > Board** and select `AI Thinker ESP32-CAM`.
4. Go to **Tools > Port** and select the FTDI COM port.
5. Click **Upload**.
6. After a successful upload, **disconnect `IO0` from `GND`** and press the RESET button on the board so the code can run.

---

## 4. Troubleshooting & Testing

- **Serial Monitor**: Always open the Serial Monitor (Baud rate: `115200`) after uploading. The microcontrollers print very detailed boot logs. 
- **Screen Issues**: If the OLED screen on the sensor node is blank, upload `ESP32/ScreenProbe/ScreenProbe.ino` to the Sensor Node to scan the I2C bus and verify the screen's hardware address.
- **ESP-NOW Not Working**: Double check that both microcontrollers are powered on, and verify that the `PARKME_CAMERA_ESPNOW_PEER_MAC` in `SECRETS.h` is exactly matching the MAC address printed by the Camera Node.
