# ParkMe Hardware Behavior

This document outlines the current behavior of the ESP32 hardware nodes in the ParkMe project, reflecting the most recent firmware updates for automation and cloud stability.

## 1. ParkMe Sensor Node (Parking Spot Monitor)
**Hardware**: ESP32 Microcontroller + HC-SR04 Ultrasonic Distance Sensor
**Purpose**: Monitors the occupancy status of individual parking spots.

### Core Behavior:
* **Distance Sampling**: The node measures distance continuously.
* **State Changes**: When a vehicle enters (distance drops below threshold) or leaves (distance returns to baseline) a parking spot, the node instantly sends a JSON POST request (`/api/v1/sensors/heartbeat`) to the server to update the database.
* **Heartbeat Mechanism (Render Keep-Alive)**: 
  * The node is configured to send a periodic "heartbeat" payload to the server every **6 minutes** (`360,000 ms`).
  * *Update*: This heartbeat is sent **unconditionally** (whether the spot is `FREE` or `OCCUPIED`). This design decision prevents the cloud backend (e.g., Render Free Tier) from going to sleep after 15 minutes of inactivity.
* **Pending Telemetry**: If the server is unreachable (WiFi drops or server crashes), the node queues the state change in its flash memory and flushes it upon the next successful connection.

## 2. ParkMe Camera Node (Entry/Exit Gate)
**Hardware**: AI Thinker ESP32-CAM + HC-SR04 Ultrasonic Distance Sensor + 16x2 I2C LCD
**Purpose**: Acts as an automated gate barrier that captures vehicle license plates for OCR processing.

### Core Behavior:
* **Automatic Vehicle Detection**: 
  * The physical push-button has been replaced by an ultrasonic distance sensor (`TRIG` on Pin 12, `ECHO` on Pin 13).
  * The `loop()` continuously monitors the distance in front of the gate barrier.
  * When an object is detected at a distance of **less than 50 cm**, the node assumes a vehicle has pulled up to the gate.
* **Automated Capture & Retry Loop**:
  1. Once a car is detected, the camera snaps a photo and POSTs it to the backend (`/api/v1/sensors/park`).
  2. The server processes the image via OpenCV and Tesseract OCR, and returns a `GateAction` (`WELCOME`, `DENIED`, or `RETRY`).
  3. **Auto-Retry**: If the server returns `RETRY` (OCR failed) or `UNKNOWN` (upload failed), the ESP32-CAM increments a counter, displays "Retrying..." on the LCD, delays for 1 second, and takes another photo.
  4. It will retry a maximum of **3 times**.
  5. Upon a successful `WELCOME` or `DENIED` response, the loop breaks, opening the gate (if welcomed) and showing the respective LCD message.
* **State Reset**: After the interaction is complete, the node displays "Please Clear gate" and goes dormant. It will not take any more photos until the ultrasonic sensor registers that the distance has exceeded 50 cm (indicating the car has driven away).
