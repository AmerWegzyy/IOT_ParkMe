# ParkMe Edge Cases & Handling Mechanisms

The ParkMe system integrates hardware sensors, camera nodes, and a cloud backend. The codebase implements several safeguards to handle asynchronous failures, hardware anomalies, and security threats.

## Backend Edge Cases (FastAPI)

1. **Hardware-Camera Asymmetry (Broken Camera)**
   - **Scenario**: A car parks, the ultrasonic sensor detects physical occupancy, but the camera node fails to capture or send an image (e.g., due to power loss, WiFi drop, or camera failure).
   - **Handling**: The `receive_heartbeat_data` endpoint detects if the physical spot is occupied but no active parking log exists. If this condition is met, it autonomously creates an entry with the license plate set to `'UNIDENTIFIED'` and flags it as a violation (`is_violation = True`).
2. **Bouncing Driver (Short Stay)**
   - **Scenario**: A driver pulls into a spot, realizes they shouldn't park there, and leaves almost immediately (within 60 seconds).
   - **Handling**: Upon departure (state transitions to `False`), the backend checks the duration of the stay. If it is under 60 seconds, it updates the log with `license_plate = 'ABORTED'` and clears any violation flags to avoid false positives and spamming administrators.
3. **Duplicate LPR Reads**
   - **Scenario**: Multiple POST requests for the same vehicle due to camera retries or bouncing frames at the gate.
   - **Handling**: The server implements an in-memory `LPR_DEDUP_CACHE` with a 5-second window. Identical plates posted within 5 seconds are ignored, returning status `"dropped"` with reason `"duplicate_within_5s"`.
4. **Replay Attacks (Spoofing)**
   - **Scenario**: A malicious actor intercepts an ESP32 HTTP POST request and resends it later to alter parking states artificially.
   - **Handling**: The `verify_hmac_signature` middleware checks the `X-Timestamp` header. If the timestamp is older than 30 seconds, it rejects the request as a Replay Attack, ensuring payloads cannot be reused.
5. **Unreadable License Plates**
   - **Scenario**: The camera sends a valid image, but the Tesseract OCR engine fails to extract any digits.
   - **Handling**: The backend responds with `{"status": "failed", "reason": "could_not_read_plate"}`. The camera node will automatically retry. If all retries fail, the spot falls back to the "Broken Camera" flow when the ultrasonic sensor posts its heartbeat.
6. **Unauthorized Parking (Role Mismatch)**
   - **Scenario**: A registered user parks in a spot reserved for a different category (e.g., a standard user parking in a "special-needs" spot).
   - **Handling**: The `receive_park_event` endpoint validates the user's role against the `spot_category`. If there is a mismatch (and the user is not an "admin"), it flags `is_violation = True` and broadcasts a real-time violation event to the admin dashboard.
7. **Admin Anomaly Resolution**
   - **Scenario**: A camera is physically blocked or broken, resulting in an `'UNIDENTIFIED'` state that needs manual correction.
   - **Handling**: The system provides a `/api/v1/sensors/resolve` endpoint, allowing an administrator to visually confirm the spot and mark the anomaly as resolved (`is_violation = FALSE` and `license_plate = 'RESOLVED'`).

## Hardware Edge Cases (ESP32 Firmware)

1. **Network Disconnection & Power Loss (Sensor Node)**
   - **Scenario**: The ultrasonic sensor loses its WiFi connection or fails to reach the backend precisely when the spot state changes.
   - **Handling**: The firmware queues the pending telemetry in non-volatile storage (NVS) via `queuePendingTelemetry()`. The `flushPendingTelemetry()` routine runs continuously in the main loop to safely transmit the saved state once connectivity is restored, surviving power reboots.
2. **Invalid Sensor Readings**
   - **Scenario**: The ultrasonic pulse returns 0 (timeout) or reports an out-of-bounds distance (e.g., > 350cm).
   - **Handling**: `classifyDistanceCm()` evaluates out-of-bound readings as `STATE_UNKNOWN`. The sensor refuses to publish an unknown state to the backend, preventing false "empty" readings if an object completely blocks the acoustic sensor.
3. **Adaptive Spot Calibration**
   - **Scenario**: The physical distance from the sensor to the floor varies per parking spot; using a hardcoded threshold causes false positives.
   - **Handling**: Holding the calibration button for 4 seconds triggers `runCalibrationMode()`. It samples the distance 15 times, averages the readings, and calculates an adaptive threshold. This baseline is saved to NVS (`preferences`) and persists across reboots.
4. **Battery Depletion Tracking**
   - **Scenario**: The sensor node's battery level drops, risking a silent failure without admin notification.
   - **Handling**: The node reads its battery voltage via a voltage divider, clamps the calculation between 0% and 100%, and appends the `battery_level` to every heartbeat payload to ensure the backend is always aware of the power state.
5. **Camera Initialization Failure**
   - **Scenario**: The ESP32-CAM module fails to communicate with the camera sensor (e.g., loose ribbon cable or unsupported PSRAM).
   - **Handling**: `initCamera()` catches the `ESP_FAIL` error, logs it, displays "Camera failed / Check wiring" on the LCD, and safely halts capture attempts to prevent kernel panics.
6. **Capture Retries (Gate Node)**
   - **Scenario**: A car arrives, but the first capture is rejected by the server (unreadable plate) or a transient network drop occurs.
   - **Handling**: The main loop implements a robust retry mechanism. If `performGateScan()` returns `ACTION_RETRY` or `ACTION_UNKNOWN`, it pauses and retries up to 3 times automatically, displaying "Retrying... X/3" on the LCD to inform the driver.
7. **LCD Buffer Overflow Protection**
   - **Scenario**: The backend sends a message that is longer than the physical LCD width (16 characters).
   - **Handling**: The helper function `fitForLcd()` automatically truncates incoming strings to exactly the column width, preventing memory corruption and visual glitches on the screen.
8. **Debouncing Gate Triggers**
   - **Scenario**: An ultrasonic sensor at the gate bounces between "present" and "not present" due to the irregular shape of a moving vehicle.
   - **Handling**: The loop uses a state latch (`carPresent`). It only triggers a scan when `isCarAtGate() == true` AND `carPresent == false`. It requires the car to move fully out of the sensor's view before resetting the latch for the next vehicle.
