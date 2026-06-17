# ParkMe Hardware Behavior

This document describes the current behavior of the ESP32 hardware nodes in the ParkMe project, reflecting the latest firmware.

## 1. ParkMe Sensor Node (Parking Spot Monitor)

**Hardware**: ESP32 + HC-SR04 Ultrasonic Distance Sensor
**Pin Configuration**: `TRIG=5`, `ECHO=18`, `BATTERY=34` (ADC via voltage divider), `CALIBRATE=0` (boot button)
**Purpose**: Monitors the occupancy status of individual parking spots.

### Core Behavior

* **Distance Sampling**: The node samples the ultrasonic sensor continuously at a **1-second interval** (`PARKME_SENSOR_SAMPLE_INTERVAL_MS = 1000`).
* **State Classification**: Readings are classified by `classifyDistanceCm()` in `ParkMeCommon.h`:
  * Distance ≤ `occupiedThresholdCm` → `STATE_OCCUPIED`
  * Distance > `occupiedThresholdCm` and ≤ `maxReliableDistanceCm` → `STATE_FREE`
  * Distance ≤ 0 or > **350 cm** (`PARKME_SENSOR_MAX_RELIABLE_DISTANCE_CM`) → `STATE_UNKNOWN` (ignored, not published)
* **State Changes**: When a known state transition occurs (FREE → OCCUPIED or OCCUPIED → FREE), the node immediately sends a JSON POST to `/api/v1/sensors/heartbeat`.
* **Heartbeat Mechanism (Render Keep-Alive)**:
  * A periodic heartbeat is sent every **6 minutes** (`PARKME_SENSOR_HEARTBEAT_INTERVAL_MS = 360000`).
  * Heartbeats are sent **unconditionally** (both `FREE` and `OCCUPIED` states) when `PARKME_SENSOR_ALLOW_FREE_HEARTBEATS = true`. This prevents the cloud backend (e.g., Render Free Tier) from sleeping after 15 minutes of inactivity.
* **NVS Telemetry Caching**: If the server is unreachable (WiFi drop or server crash), the node queues the pending state change in non-volatile storage (NVS) via `queuePendingTelemetry()`. The `flushPendingTelemetry()` routine runs in the main loop and transmits saved states once connectivity is restored. Cached data survives power reboots.
* **Battery Monitoring**: The node reads battery voltage via an ADC pin through a voltage divider, clamps the percentage between 0–100% using `batteryPercentFromVoltage()`, and appends `battery_level` to every heartbeat payload.
* **Adaptive Calibration**: Holding the calibration button (GPIO 0) for **4 seconds** triggers `runCalibrationMode()`. It takes **15 samples**, averages the readings, and saves the baseline to NVS. The occupied threshold is computed as `baseline − 30 cm` (delta), with a minimum floor of **8 cm** (`PARKME_SENSOR_MIN_THRESHOLD_CM`).

### Networking

* **WiFi Retry**: Reconnects every **10 seconds** (`PARKME_SENSOR_WIFI_RETRY_INTERVAL_MS = 10000`).
* **HTTP Timeout**: **5 seconds** (`PARKME_SENSOR_HTTP_TIMEOUT_MS = 5000`).

---

## 2. ParkMe Camera Node (Entry/Exit Gate)

**Hardware**: AI Thinker ESP32-CAM + HC-SR04 Ultrasonic Distance Sensor + 16×2 I2C LCD + Relay (optional)
**Pin Configuration**: `TRIG=12`, `ECHO=13`, `FLASH_LED=4`, `RELAY=-1` (disabled by default), LCD `SDA=14`, `SCL=15` (I2C address `0x27`)
**Purpose**: Acts as an automated gate barrier that captures vehicle license plates for cloud-based OCR.

### Core Behavior

* **Automatic Vehicle Detection**:
  * The `loop()` continuously calls `isCarAtGate()`, which reads the ultrasonic sensor.
  * A vehicle is detected when the distance is **greater than 0 and less than 50 cm**.
* **State Latch (Debouncing)**: A boolean `carPresent` latch prevents re-triggering. A scan only begins when `isCarAtGate() == true` AND `carPresent == false`. The latch resets only after the car fully clears the sensor (distance ≥ 50 cm).
* **Flash LED**: GPIO 4 fires an **80 ms HIGH pulse** immediately before `esp_camera_fb_get()` to illuminate the plate, then turns LOW.
* **PSRAM-Aware Camera Config**: The firmware detects PSRAM at runtime via `psramFound()`:
  * **With PSRAM**: VGA resolution, JPEG quality 10, 2 frame buffers.
  * **Without PSRAM**: QVGA resolution, JPEG quality 12, 1 frame buffer.
* **Automated Capture & Retry Loop**:
  1. Once a car is detected, the camera captures a frame and POSTs the JPEG image to `/api/v1/sensors/park` using **raw HTTP/1.1 over TCP** (multipart/form-data), not the Arduino `HTTPClient` library.
  2. The backend processes the image via **Google Cloud Vision API** (`google.cloud.vision`) for text detection and returns a JSON response containing `action` and `message` keys.
  3. The firmware parses the `action` field using the `parseGateAction()` function from `ParkMeCommon.h`, which maps it to the `GateAction` enum: `ACTION_WELCOME`, `ACTION_DENIED`, `ACTION_RETRY`, or `ACTION_UNKNOWN`.
  4. **Auto-Retry**: If the action is `ACTION_RETRY` (OCR failed) or `ACTION_UNKNOWN` (upload/parse failure), the node increments a counter, displays "Retrying… X/3" on the LCD, pauses for 1 second, and retakes the photo. Maximum **3 attempts**.
  5. On `ACTION_WELCOME`: the relay (if configured, `PARKME_GATE_RELAY_PIN ≥ 0`) fires a **3-second HIGH pulse** (`PARKME_GATE_RELAY_PULSE_MS = 3000`) to open the gate barrier.
  6. On `ACTION_DENIED`: a denial message is shown on the LCD. No relay action.
* **No Caching**: Unlike the Sensor Node, the Camera Node does **not** cache failed uploads. If all retries fail, the spot falls back to the "ghost log" flow when the heartbeat detects physical occupancy without an active parking log.
* **State Reset**: After the interaction completes, the LCD displays "Please / Clear gate". The node goes dormant until the ultrasonic sensor registers the car has left (distance ≥ 50 cm), which resets `carPresent` and shows "Ready to scan / Approach gate".

### Networking

* **WiFi Retry**: Reconnects every **10 seconds** (`PARKME_GATE_WIFI_RETRY_INTERVAL_MS = 10000`).
* **HTTP Timeout**: **10 seconds** (`PARKME_GATE_HTTP_TIMEOUT_MS = 10000`).
* **Transport**: Raw `WiFiClient` / `WiFiClientSecure` TCP sockets with manually constructed HTTP/1.1 requests (multipart boundary for image upload). Uses `setInsecure()` for TLS (no certificate pinning).

---

## 3. Shared Library (`ParkMeCommon.h`)

Both nodes share a header-only library providing:
* **Enums**: `SpotState` (`FREE`, `OCCUPIED`, `UNKNOWN`) and `GateAction` (`UNKNOWN`, `WELCOME`, `DENIED`, `RETRY`).
* **Pure functions** (many `constexpr`): `classifyDistanceCm()`, `computeOccupiedThreshold()`, `batteryPercentFromVoltage()`, `parseGateAction()`, `fitForLcd()`, `buildServerUrl()`, `makeHeartbeatPayload()`, etc.
* **`parseGateAction()`**: A compile-time string matcher that looks for `"action":"WELCOME"`, `"action":"DENIED"`, or `"action":"RETRY"` in the raw JSON payload.

## 4. Configuration (`SECRETS.h`)

All pin assignments, server endpoints, timeouts, and calibration defaults are defined in `SECRETS.h` (copied from `SECRETS.example.h`). The file `parameters.h` is **legacy/unused**.

> **Note**: `PARKME_GATE_DEBOUNCE_MS` exists in `SECRETS.example.h` but is **never referenced** in any firmware code. Gate debouncing is handled entirely by the `carPresent` boolean latch.
