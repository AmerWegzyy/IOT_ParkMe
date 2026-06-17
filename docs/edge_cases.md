# ParkMe Edge Cases & Handling Mechanisms

The ParkMe system integrates hardware sensors, camera nodes, and a cloud backend. The codebase implements several safeguards to handle asynchronous failures, hardware anomalies, and security threats.

---

## Backend Edge Cases (FastAPI)

### 1. Hardware-Camera Asymmetry (Ghost Log / Broken Camera)

- **Scenario**: A car parks, the ultrasonic sensor detects physical occupancy, but the camera node fails to capture or send an image (e.g., due to power loss, WiFi drop, or camera failure).
- **Handling**: The `receive_heartbeat_data` endpoint detects that the physical spot is occupied but no active parking log exists. It autonomously creates a log entry with `license_plate = 'UNIDENTIFIED'` and flags it as a violation (`is_violation = True`). This is referred to as a "ghost log."

### 2. Ghost Log Self-Healing

- **Scenario**: A ghost log exists (plate = `UNIDENTIFIED`) when the camera finally succeeds in capturing and identifying the plate.
- **Handling**: The `receive_park_event` endpoint (park) checks for any active `UNIDENTIFIED` log on the same spot. If one is found, it **overwrites** the ghost log with the real license plate, user data, and violation status rather than creating a duplicate entry. This resolves the anomaly automatically without admin intervention.

### 3. Bouncing Driver (Short Stay)

- **Scenario**: A driver pulls into a spot, realizes they shouldn't park there, and leaves almost immediately (within 60 seconds).
- **Handling**: Upon departure (sensor state transitions to `FREE`), the backend checks the duration of the stay. If it is under **60 seconds**, it updates the log with `license_plate = 'ABORTED'` and sets `is_violation = False` to avoid false positives and unnecessary admin alerts.

### 4. Duplicate LPR Reads (Dedup Cache)

- **Scenario**: Multiple POST requests arrive for the same vehicle due to camera retries or bouncing frames at the gate.
- **Handling**: The server maintains an in-memory `LPR_DEDUP_CACHE` with a **5-second window**. If an identical plate is submitted within 5 seconds of the previous submission, the request is dropped and the server responds with `status: "dropped"` and `reason: "duplicate_within_5s"`.


### 6. Unreadable License Plates

- **Scenario**: The camera sends a valid image, but the **Google Cloud Vision API** fails to extract any text from the plate.
- **Handling**: The backend responds with `{"action": "RETRY", "message": "could_not_read_plate"}`. The camera node will automatically retry (up to 3 times). If all retries fail, the spot falls back to the ghost log flow when the ultrasonic sensor sends its next heartbeat.

### 7. Unauthorized Parking (Role Mismatch)

- **Scenario**: A registered user parks in a spot reserved for a different category (e.g., a standard user parking in a "special-needs" spot).
- **Handling**: The `receive_park_event` endpoint validates the user's role against the `spot_category`. If there is a mismatch (and the user is not an "admin"), it flags `is_violation = True` and broadcasts a real-time violation event to the admin dashboard via WebSocket.

### 8. Admin Anomaly Resolution

- **Scenario**: A camera is physically blocked or broken, resulting in an `UNIDENTIFIED` parking log that requires manual correction.
- **Handling**: The system provides a `/api/v1/sensors/resolve` endpoint, allowing an administrator to visually confirm the spot and mark the anomaly as resolved (`is_violation = FALSE` and `license_plate = 'RESOLVED'`).

---

## Hardware Edge Cases (ESP32 Firmware)

### 1. Network Disconnection & Telemetry Caching (Sensor Node)

- **Scenario**: The ultrasonic sensor node loses its WiFi connection or fails to reach the backend precisely when the spot state changes.
- **Handling**: The firmware queues the pending telemetry in non-volatile storage (NVS) via `queuePendingTelemetry()`. The `flushPendingTelemetry()` routine runs continuously in the main loop and transmits the saved state once connectivity is restored. Cached data survives power reboots.
- **WiFi Retry**: The sensor node retries WiFi connection every **10 seconds** (`PARKME_SENSOR_WIFI_RETRY_INTERVAL_MS = 10000`).
- **HTTP Timeout**: **5 seconds** (`PARKME_SENSOR_HTTP_TIMEOUT_MS = 5000`).

### 2. Network Failure at the Gate (Camera Node)

- **Scenario**: The camera node fails to connect to the backend during a gate scan.
- **Handling**: The camera node does **not** cache failed uploads (unlike the sensor node). `performGateScan()` returns `ACTION_UNKNOWN` on connection failure, and the retry loop will attempt up to **3 times**. If all fail, the LCD displays "Please / Clear gate" and the node waits for the car to leave. The spot will be covered by the ghost log mechanism when the sensor heartbeat detects occupancy without a parking log.
- **WiFi Retry**: Reconnects every **10 seconds** (`PARKME_GATE_WIFI_RETRY_INTERVAL_MS = 10000`).
- **HTTP Timeout**: **10 seconds** (`PARKME_GATE_HTTP_TIMEOUT_MS = 10000`).

### 3. Invalid Sensor Readings

- **Scenario**: The ultrasonic pulse returns 0 (timeout) or reports an out-of-bounds distance (> 350 cm).
- **Handling**: `classifyDistanceCm()` in `ParkMeCommon.h` evaluates these as `STATE_UNKNOWN`. The sensor node refuses to publish an unknown state, preventing false "empty" readings if an object completely blocks the acoustic sensor or if the pulse times out.

### 4. Adaptive Spot Calibration

- **Scenario**: The physical distance from the sensor to the floor varies per parking spot; using a hardcoded threshold causes false positives.
- **Handling**: Holding the calibration button (GPIO 0) for **4 seconds** triggers `runCalibrationMode()`. It takes **15 distance samples**, averages the readings, and computes an adaptive threshold: `baseline − 30 cm`, with a minimum floor of **8 cm**. The baseline is saved to NVS (`preferences`) and persists across reboots.

### 5. Battery Depletion Tracking

- **Scenario**: The sensor node's battery level drops, risking silent failure without admin notification.
- **Handling**: The node reads battery voltage via a voltage divider on the ADC pin (GPIO 34), clamps the calculation between 0–100% using `batteryPercentFromVoltage()`, and appends `battery_level` to every heartbeat payload so the backend is always aware of the power state.

### 6. Camera Initialization Failure

- **Scenario**: The ESP32-CAM module fails to communicate with the camera sensor (e.g., loose ribbon cable or unsupported PSRAM configuration).
- **Handling**: `initCamera()` catches the `ESP_FAIL` error, logs it to serial, displays "Camera failed / Check wiring" on the LCD, and safely halts capture attempts to prevent kernel panics. The firmware detects PSRAM at runtime via `psramFound()` and adjusts resolution (VGA vs QVGA), JPEG quality (10 vs 12), and frame buffer count (2 vs 1) accordingly.

### 7. Capture Retries (Gate Node)

- **Scenario**: A car arrives, but the first capture is rejected by the server (unreadable plate) or a transient network error occurs.
- **Handling**: The main loop implements a retry mechanism. If `performGateScan()` returns `ACTION_RETRY` or `ACTION_UNKNOWN`, it pauses for 1 second and retries up to **3 times** total, displaying "Retrying… X/3" on the LCD. On `ACTION_WELCOME`, the relay fires a **3-second HIGH pulse** (if `PARKME_GATE_RELAY_PIN ≥ 0`). On `ACTION_DENIED`, a denial message is displayed with no relay action.

### 8. LCD Buffer Overflow Protection

- **Scenario**: The backend sends a message longer than the physical LCD width (16 characters).
- **Handling**: The helper function `fitForLcd()` in `ParkMeCommon.h` truncates incoming strings to exactly the column width, preventing memory corruption and visual glitches.

### 9. Debouncing Gate Triggers

- **Scenario**: The ultrasonic sensor at the gate fluctuates between "present" and "not present" due to the irregular shape of a moving vehicle.
- **Handling**: The loop uses a **boolean state latch** (`carPresent`). It only triggers a scan when `isCarAtGate() == true` AND `carPresent == false`. The latch sets to `true` on detection and only resets to `false` after the car fully clears the sensor (distance ≥ 50 cm), preventing re-triggering during a single vehicle interaction.

> **Note**: The constant `PARKME_GATE_DEBOUNCE_MS` exists in `SECRETS.example.h` but is **never referenced** in the camera node firmware. All debouncing is handled by the `carPresent` latch.

### 10. Flash LED Timing

- **Scenario**: The onboard flash LED must illuminate the license plate during capture without staying on indefinitely and overheating.
- **Handling**: GPIO 4 is driven HIGH for exactly **80 ms** before `esp_camera_fb_get()` is called, then immediately driven LOW. The LED is only activated if `PARKME_GATE_FLASH_LED_PIN ≥ 0`.
