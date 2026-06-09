# ParkMe: ESP32 Hardware Integration Spec

This document is for the hardware developer writing the ESP32-CAM code in the Arduino IDE. It explicitly defines how the FastAPI backend expects the hardware to behave, ensuring 100% compatibility for our Edge Sensor Fusion architecture.

---

## Overview: Edge Sensor Fusion
Our backend relies on the ESP32 to act as the authoritative edge node. The server does **not** poll the hardware; the hardware must push events to the server. 

The ESP32 is responsible for two distinct workflows:
1. **Heartbeat & Telemetry**: Sending continuous updates on physical occupancy and battery life.
2. **LPR Capture**: Snapping and uploading an image ONLY when a car physically arrives.

---

## 1. The Heartbeat API
The backend requires a continuous physical state feed to detect anomalies (like broken cameras) and to monitor battery life.

**Endpoint:** `POST /api/v1/sensors/heartbeat`
**Content-Type:** `application/json`

### Trigger Conditions
You must fire an HTTP POST request to this endpoint under two conditions:
1. **Periodic Sync**: Every 60 seconds (to prove the node hasn't died and to update battery).
2. **State Change**: IMMEDIATELY when the ultrasonic sensor detects a change (car arrives OR car leaves).

### JSON Payload Schema
```json
{
  "mac_address": "44:44:44:44:44:44",
  "is_occupied": true,
  "battery_level": 85.5
}
```
*Note: `battery_level` must be a float between 0 and 100.*

### Security Headers (HMAC-SHA256)
To prevent spoofing, the backend expects two custom headers:
* `X-Timestamp`: The current Unix timestamp.
* `X-Signature`: An HMAC-SHA256 hash of the string `<timestamp>.<json_body>` using our shared secret key.
*(Note: If you are testing locally, the backend currently ignores missing signatures, but you should build this into the `HTTPClient` logic for production).*

---

## 2. The LPR Image Upload (Park API)
The backend runs Tesseract OCR. The ESP32 is strictly responsible for capturing a clear JPEG and uploading it.

**Endpoint:** `POST /api/v1/sensors/park`
**Content-Type:** `multipart/form-data`

### Trigger Conditions
You must fire this HTTP POST request **ONLY** when the ultrasonic sensor detects a transition from `is_occupied: false` to `is_occupied: true`. 
1. Car Arrives -> Ultrasonic triggers -> Fire `heartbeat` with `true` -> Wake up OV2640 -> Snap Photo -> Fire `park` with image.
2. Car Leaves -> Ultrasonic triggers -> Fire `heartbeat` with `false`. *(Do NOT take a photo when a car leaves)*.

### Form-Data Payload
The backend requires a strict multipart form structure using the `HTTPClient` library:
1. **`spot_id`** (Text Field): A string representing the physical spot ID (e.g., `"444"` or `"555"`).
2. **`file`** (File Field): The raw JPEG buffer from `esp_camera_fb_get()`.

### Example Arduino HTTP Form Structure
Ensure your `boundary` logic correctly maps to these keys:
```text
--boundary_string
Content-Disposition: form-data; name="spot_id"

444
--boundary_string
Content-Disposition: form-data; name="file"; filename="capture.jpg"
Content-Type: image/jpeg

<RAW JPEG BYTES HERE>
--boundary_string--
```

---

## Common Pitfalls to Avoid
1. **Never send images continuously**: Video streaming will crash the backend. Only send exactly one image per physical arrival event.
2. **Do not forget the Exit heartbeat**: When a car leaves, the backend relies 100% on the ESP32 sending a `heartbeat` with `is_occupied: false` to end the parking session and free up the spot in the database.
3. **Wait for WiFi**: The ESP32-CAM draws massive current when the camera and WiFi radio run simultaneously. If you encounter brownout resets, ensure you capture the frame into PSRAM *before* turning on the WiFi radio to transmit.
