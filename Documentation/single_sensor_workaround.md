# Single Sensor Workaround (Dual Board Setup)

This document explains how to run the full ParkMe physical demonstration (using both the ESP32-CAM and the normal ESP32) when you only have **one** physical HC-SR04 ultrasonic sensor.

## The Architecture
The ParkMe system is designed to use two separate sensors (one for the gate, one for the spot). To simulate this with one sensor, we use a **digital jumper wire**. 
When the ultrasonic sensor detects a car, the Normal ESP32 sends a heartbeat to the server AND shoots a 3.3V signal across the jumper wire to the ESP32-CAM. The ESP32-CAM feels this signal and instantly takes the picture.

---

## 1. Firmware Uploading Guide

You have two different codebases. You must compile and upload them to their respective boards using the Arduino IDE.

### For the Normal ESP32 (Spot Node)
* **Directory to open:** `ESP32/ParkMeSensorNode/`
* **File to flash:** `ParkMeSensorNode.ino`
* **Dependencies:** Make sure you have created your `SECRETS.h` file in this directory with your Wi-Fi credentials.

### For the ESP32-CAM (Gate Node)
* **Directory to open:** `ESP32/ParkMeCameraNode/`
* **File to flash:** `ParkMeCameraNode.ino`
* **Dependencies:** Make sure you have created your `SECRETS.h` file in this directory with your Wi-Fi credentials.

---

## 2. Comprehensive Wiring Guide

Make sure all boards are powered off before wiring.

### A. Ultrasonic Sensor (HC-SR04) -> Normal ESP32
* **VCC** -> `5V` (or `VIN`) on Normal ESP32
* **GND** -> `GND` on Normal ESP32
* **Trig** -> `Pin 5` on Normal ESP32
* **Echo** -> `Pin 18` on Normal ESP32

### B. Board-to-Board Communication (The Jumper Wire)
* **Signal Wire:** Connect `Pin 4` on the Normal ESP32 to `Pin 12` on the ESP32-CAM.
* **Common Ground:** Connect any `GND` pin on the Normal ESP32 to any `GND` pin on the ESP32-CAM. *(Critical: They must share a ground to read the signal properly!)*

### C. I2C LCD Display -> ESP32-CAM
* **VCC** -> `5V` on ESP32-CAM
* **GND** -> `GND` on ESP32-CAM
* **SDA** -> `Pin 14` on ESP32-CAM
* **SCL** -> `Pin 15` on ESP32-CAM

---

## 3. Required Code Modifications

You must make the following small tweaks to the `.ino` files so they know to use the jumper wire instead of looking for a second sensor.

### Modify the Normal ESP32 (`ParkMeSensorNode.ino`)
We need to configure Pin 4 to send the 3.3V signal when the spot is occupied.

1. **Inside `setup()`**, add:
   ```cpp
   pinMode(4, OUTPUT);
   digitalWrite(4, LOW);
   ```

2. **Inside `loop()`**, look for where the heartbeat is sent. 
   When `is_occupied` is true (car detected), add:
   ```cpp
   digitalWrite(4, HIGH);
   ```
   When `is_occupied` is false (car leaves), add:
   ```cpp
   digitalWrite(4, LOW);
   ```

### Modify the ESP32-CAM (`ParkMeCameraNode.ino`)
We need to bypass the ultrasonic reading and just listen for the 3.3V signal on Pin 12.

1. **Find the `isCarAtGate()` function** and replace it entirely with this:
   ```cpp
   bool isCarAtGate() {
     // Read the signal wire from the Normal ESP32 instead of a sensor
     return digitalRead(12) == HIGH;
   }
   ```

2. **Inside `setup()`**, ensure Pin 12 is set as an input:
   ```cpp
   pinMode(12, INPUT_PULLDOWN);
   ```
