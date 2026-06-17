# ParkMe: ESP32 Hardware Integration Spec

This document is for the hardware developer writing the ESP32-CAM code in the Arduino IDE. It explicitly defines how the FastAPI backend expects the hardware to behave, ensuring 100% compatibility for our Edge Sensor Fusion architecture.

---

## Overview: Edge Sensor Fusion
Our backend relies on the ESP32 to act as the authoritative edge node. The server does **not** poll the hardware; the hardware must push events to the server. 

The ESP32 is responsible for two distinct workflows:
1. **Heartbeat & Telemetry**: Sending periodic updates on physical occupancy and battery life.
2. **LPR Capture**: Snapping and uploading a JPEG image ONLY when a car physically arrives.

---

## 1. The Heartbeat API
The backend requires a periodic physical state feed to detect anomalies (like broken cameras) and to monitor battery life.

**Endpoint:** `POST /api/v1/sensors/heartbeat`  
**Content-Type:** `application/json`  
**Response:** `202 Accepted`

### Trigger Conditions
You must fire an HTTP POST request to this endpoint under two conditions:
1. **Periodic Sync**: Every **6 minutes** (360,000 ms) — to prove the node hasn't died and to update battery level.
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

> **Note:** The backend resolves the parking spot by querying the `parking_spots` Firestore collection for the document whose `sensor_mac` field matches the provided `mac_address`. There is no `spot_id` in this payload.

### NVS Caching (Sensor Node Only)
The Sensor Node firmware includes NVS (Non-Volatile Storage) caching for failed telemetry POSTs. If the HTTP request fails (e.g., server unreachable), the reading is stored in NVS and retried on the next cycle. This ensures no heartbeat data is silently lost during network outages.

---

## 2. The LPR Image Upload (Park API)
The backend runs **Google Cloud Vision API** for license-plate recognition. The ESP32 is strictly responsible for capturing a clear JPEG and uploading it — no preprocessing or OCR happens on the device.

**Endpoint:** `POST /api/v1/sensors/park`  
**Content-Type:** `multipart/form-data`

### Trigger Conditions
You must fire this HTTP POST request **ONLY** when the ultrasonic sensor detects a transition from `is_occupied: false` to `is_occupied: true`. 
1. Car Arrives -> Ultrasonic triggers -> Fire `heartbeat` with `true` -> Wake up OV2640 -> Snap Photo -> Fire `park` with image.
2. Car Leaves -> Ultrasonic triggers -> Fire `heartbeat` with `false`. *(Do NOT take a photo when a car leaves)*.

### Form-Data Payload
The Camera Node uses **raw HTTP/1.1 over TCP** (`WiFiClient`), NOT the Arduino `HTTPClient` library. The firmware manually constructs the HTTP request headers and multipart body, then writes them byte-by-byte to the TCP socket. The backend requires a strict multipart form structure:
1. **`camera_mac`** (Text Field): The MAC address of this ESP32-CAM node (e.g., `"AA:BB:CC:DD:EE:02"`). The backend dynamically resolves the `spot_id` by querying Firestore for the matching `camera_mac`.
2. **`file`** (File Field): The raw JPEG buffer from `esp_camera_fb_get()`.

### Example Arduino HTTP Form Structure
Ensure your `boundary` logic correctly maps to these keys:
```text
--boundary_string
Content-Disposition: form-data; name="camera_mac"

AA:BB:CC:DD:EE:02
--boundary_string
Content-Disposition: form-data; name="file"; filename="capture.jpg"
Content-Type: image/jpeg

<RAW JPEG BYTES HERE>
--boundary_string--
```

### Response Handling & Retry Logic
The backend responds with a JSON object containing an `action` field. The Camera Node firmware should parse this field and react accordingly:
* **`"WELCOME"` or `"DENIED"`**: The request was processed successfully. Do not retry.
* **`"RETRY"`**: The backend could not read the plate or encountered a transient issue. The firmware should retry the capture and upload, up to **3 attempts**.
* **Unknown / HTTP error**: Treat as retriable. The firmware retries up to 3 times.

> **Note:** Unlike the Sensor Node, the Camera Node does **not** have NVS caching for failed uploads. If all 3 retries fail, the image is lost.

---

## Common Pitfalls to Avoid
1. **Never send images continuously**: Video streaming will crash the backend. Only send exactly one image per physical arrival event.
2. **Do not forget the Exit heartbeat**: When a car leaves, the backend relies 100% on the ESP32 sending a `heartbeat` with `is_occupied: false` to end the parking session and free up the spot in the database.
3. **Wait for WiFi**: The ESP32-CAM draws massive current when the camera and WiFi radio run simultaneously. If you encounter brownout resets, ensure you capture the frame into PSRAM *before* turning on the WiFi radio to transmit.
4. **Raw TCP, not HTTPClient**: The Camera Node builds HTTP requests manually over a `WiFiClient` TCP connection. If you're modifying the camera firmware, do not try to swap in the `HTTPClient` library without updating all the header/body construction logic.
5. **MAC addresses are strings**: The heartbeat payload uses `mac_address` and the park endpoint uses `camera_mac`. Both are string fields. The backend resolves the logical spot ID from these MAC addresses automatically.
6. **6-minute heartbeat, not 60 seconds**: The periodic heartbeat interval is 360,000 ms (6 minutes). Sending every 60 seconds would drain the battery unnecessarily and generate excessive traffic.
