# ParkMe — Hardware Behavior, Edge Cases & Backend Integration

This document outlines the detailed behaviors, state machines, edge case handling, and network integration of the ParkMe hardware nodes (**Sensor Node** and **Camera/Gate Node**) with the **FastAPI Backend**, including critical API discrepancies discovered between the ESP32 firmware and the server-side code.

---

## 1. Hardware Node Architecture

The ParkMe physical layer consists of two types of nodes deployed on ESP32 microcontrollers:

1.  **Sensor Node ([ParkMeSensorNode.ino](file:///mnt/c/Users/aamer/OneDrive/Desktop/TECHNION/SEMESTER6/IOT/parkme_project/IOT_ParkMe/ESP32/ParkMeSensorNode/ParkMeSensorNode.ino)):**
    *   **Purpose:** Monitors individual parking spots to detect physical vehicle occupancy (occupied/free) and tracks battery voltage.
    *   **Sensors:** Ultrasonic sensor (HC-SR04) for distance measurement, battery voltage meter via ADC.
    *   **I/O Pinout (Configured in [SECRETS.example.h](file:///mnt/c/Users/aamer/OneDrive/Desktop/TECHNION/SEMESTER6/IOT/parkme_project/IOT_ParkMe/ESP32/SECRETS.example.h)):**
        *   Trigger Pin: `5` (GPIO 5)
        *   Echo Pin: `18` (GPIO 18)
        *   Battery Pin: `34` (GPIO 34, ADC1)
        *   Calibrate Pin: `0` (GPIO 0, Boot button)

2.  **Camera/Gate Node ([ParkMeCameraNode.ino](file:///mnt/c/Users/aamer/OneDrive/Desktop/TECHNION/SEMESTER6/IOT/parkme_project/IOT_ParkMe/ESP32/ParkMeCameraNode/ParkMeCameraNode.ino)):**
    *   **Purpose:** Acts as a gate barrier control system. Detects arriving cars, captures license plate snapshots, requests access permission from the backend, and operates the physical gate barrier.
    *   **Sensors:** OV2640 Camera module, Ultrasonic sensor (HC-SR04) for arrival detection, I2C LCD display (16x2), relay for gate barrier control.
    *   **I/O Pinout (Configured in [SECRETS.example.h](file:///mnt/c/Users/aamer/OneDrive/Desktop/TECHNION/SEMESTER6/IOT/parkme_project/IOT_ParkMe/ESP32/SECRETS.example.h)):**
        *   Trigger Pin: `12` (GPIO 12)
        *   Echo Pin: `13` (GPIO 13)
        *   Flash LED Pin: `4` (GPIO 4)
        *   Relay Pin: `-1` (Not assigned / custom GPIO)
        *   I2C LCD SDA/SCL: `14` / `15` (GPIO 14/15)

---

## 2. Core Hardware Behaviors & State Machines

### A. Proximity Sensing & State Classification
Both nodes utilize the HC-SR04 ultrasonic sensor. 
*   **Measurement:** The node triggers a 10µs high pulse on the Trig pin and listens on the Echo pin using `pulseIn()` with a 30,000µs timeout.
*   **Conversion:** `distanceCm = (durationUs * 0.0343f) / 2.0f`.
*   **Classification ([ParkMeCommon.h](file:///mnt/c/Users/aamer/OneDrive/Desktop/TECHNION/SEMESTER6/IOT/parkme_project/IOT_ParkMe/ESP32/ParkMeCommon/ParkMeCommon.h#L39-L46)):**
    *   `STATE_UNKNOWN`: Distance is $\le 0$ (timeout) or $> 350\text{ cm}$ (max reliable range).
    *   `STATE_OCCUPIED`: Distance is $\le \text{occupiedThresholdCm}$.
    *   `STATE_FREE`: Distance is $>\text{occupiedThresholdCm}$ and $\le 350\text{ cm}$.

### B. Sensor Node Calibration Mode
*   **Trigger:** Triggered on boot if the GPIO 0 button is held, or during runtime if held for $\ge 4\text{ seconds}$.
*   **Execution:** Takes 15 valid samples with a 120ms delay. If successful, averages the values and writes the baseline distance to non-volatile storage (`Preferences` key `"base_cm"`).
*   **Formula:** The new occupied threshold is calculated as:
    $$\text{Threshold} = \text{Baseline} - 30\text{ cm}$$
    It is clamped to a minimum of $8\text{ cm}$ to prevent false triggers.

### C. Gate Node Arrival Detection & Relays
*   **Trigger:** When a car is detected at $\le 50\text{ cm}$ of the gate.
*   **State Locking:** A simple latch logic (`carPresent` boolean flag) ensures the scan runs exactly once when the vehicle arrives. The scan is locked until the vehicle departs ($>50\text{ cm}$).
*   **Capture & Flash:** When triggered, the board turns on the high-power onboard white LED (GPIO 4) for 80ms, captures a frame, and turns it off to capture clear license plates even at night.
*   **Gate Operation:** If the backend responds with a welcome status, the node activates the gate relay (GPIO configuration `PARKME_GATE_RELAY_PIN`) with a high-state pulse of 3,000ms.

---

## 3. Edge-Case Handlings

### A. Hardware-Level Resiliency
1.  **Network Reconnection Routine (`maintainWiFi`):**
    If the Wi-Fi connection drops, the nodes do not block execution. They check the connection asynchronously and try to reconnect every 10 seconds (`PARKME_SENSOR_WIFI_RETRY_INTERVAL_MS`).
2.  **Offline Telemetry Queueing (Sensor Node):**
    If the Sensor Node fails to report state updates to the server (e.g. server is down or network timeout), it writes the failed state, spot ID, and battery percentage to ESP32 Flash memory (`Preferences` key `"pending"`).
    Once Wi-Fi restores, the background loop calls `flushPendingTelemetry()` to upload the queue and clears the memory.
3.  **Low-Light Image Capture (Gate Node):**
    Synchronizes the flash LED with the camera capture buffer frame retrieval to prevent underexposed OCR attempts.
4.  **Camera Memory Constraints:**
    The Camera Node detects if PSRAM is present on the ESP32-CAM board. If PSRAM is found, it captures high-resolution VGA images (`FRAMESIZE_VGA` / Quality 10). If no PSRAM is detected, it falls back to QVGA (`FRAMESIZE_QVGA` / Quality 12) to avoid running out of memory.

### B. Backend-Level Resiliency ([main.py](file:///mnt/c/Users/aamer/OneDrive/Desktop/TECHNION/SEMESTER6/IOT/parkme_project/IOT_ParkMe/Backend/main.py))
1.  **Replay Attack Prevention (HMAC Security):**
    When HMAC headers (`X-Signature` and `X-Timestamp`) are supplied, the backend compares the timestamp with server time. If the request is older than 30 seconds, it's rejected as a replay attack.
2.  **LPR Double-trigger Deduplication:**
    To prevent multiple database writes for a single vehicle arrival, `main.py` maintains an in-memory deduplication cache (`LPR_DEDUP_CACHE`). If the same license plate is read again within 5 seconds, the request is dropped.
3.  **Bouncing Drivers (Aborted Sessions):**
    If a car occupies a spot but departs in under 60 seconds, the backend marks the log exit time and overrides the license plate record to `"ABORTED"`, setting `is_violation = False` to prevent penalty triggers.
4.  **Ghost Cars (Unidentified Occupancy) & OCR Race-Condition Resolution:**
    If the Sensor Node reports `is_occupied: true` but the Camera Node failed to capture or read a license plate, the backend creates an automatic log labeled `"UNIDENTIFIED"` and flags it as a violation.
    **Self-Healing Logic:** Since the parking spot utilizes a combined sensor/camera architecture, the camera may be executing a 5-second auto-retry loop while the ultrasonic sensor has already triggered the ghost car alarm. If the camera eventually succeeds on a 2nd or 3rd retake, the backend's `receive_park_event` endpoint actively detects the `UNIDENTIFIED` ghost log and overwrites it with the valid driver data. This automatically clears the violation status and removes the "Acknowledge & Resolve" button from the Admin Dashboard.

---

## 4. Communication Protocol & Mismatch Analysis

During code analysis, **critical API mismatches** were identified between the ESP32 Camera Node firmware and the FastAPI backend responses for the gate verification endpoint `POST /api/v1/sensors/park`.

### Discrepancy 1: Response Action Key
*   **ESP32 Expectation ([ParkMeCommon.h](file:///mnt/c/Users/aamer/OneDrive/Desktop/TECHNION/SEMESTER6/IOT/parkme_project/IOT_ParkMe/ESP32/ParkMeCommon/ParkMeCommon.h#L91-L99)):**
    The firmware parses the HTTP response string looking for `"action":"WELCOME"`, `"action":"DENIED"`, or `"action":"RETRY"`.
*   **FastAPI Backend ([main.py](file:///mnt/c/Users/aamer/OneDrive/Desktop/TECHNION/SEMESTER6/IOT/parkme_project/IOT_ParkMe/Backend/main.py#L362-L367)):**
    The backend returns a JSON payload without an `action` key:
    ```json
    {
      "status": "park_recorded",
      "plate": "123456",
      "is_violation": false,
      "display_message": "welcome Driver Name"
    }
    ```
*   **Result:** The ESP32's `parseGateAction` returns `ACTION_UNKNOWN`. The camera node falls back to its `default` switch statement, displaying **"Server error / Unexpected data"** on the screen and **refusing to open the gate** (relay is never pulsed).

### Discrepancy 2: Response Message Key
*   **ESP32 Expectation ([ParkMeCameraNode.ino](file:///mnt/c/Users/aamer/OneDrive/Desktop/TECHNION/SEMESTER6/IOT/parkme_project/IOT_ParkMe/ESP32/ParkMeCameraNode/ParkMeCameraNode.ino#L234)):**
    The firmware extracts the message string from the JSON using `"message"`.
*   **FastAPI Backend ([main.py](file:///mnt/c/Users/aamer/OneDrive/Desktop/TECHNION/SEMESTER6/IOT/parkme_project/IOT_ParkMe/Backend/main.py#L366)):**
    The backend returns `"display_message": "..."` instead of `"message": "..."`.
*   **Result:** The ESP32's parser successfully extracts the message by accident because the substring search `\"message\":\"` matches the end of `\"display_message\":\"`. However, this is an brittle side effect that breaks if the keys are reformatted.

---

## 5. Recommendations to Fix the Mismatch

To align the backend response with the hardware expectations, the return payload in the backend's `receive_park_event` endpoint inside [main.py](file:///mnt/c/Users/aamer/OneDrive/Desktop/TECHNION/SEMESTER6/IOT/parkme_project/IOT_ParkMe/Backend/main.py) should be modified.

### Proposed Backend JSON Response Fix:
```python
    # For a successful check-in
    action = "WELCOME" if not is_violation else "DENIED"
    return {
        "status": "park_recorded", 
        "plate": license_plate, 
        "is_violation": is_violation,
        "action": action,
        "message": display_message
    }
```

```python
    # For a failed OCR attempt
    if not license_plate:
        return {
            "status": "failed", 
            "reason": "could_not_read_plate",
            "action": "RETRY",
            "message": "Scan again"
        }
```

---

## 5. Server Logging Lifecycle & Database Mutations

The backend meticulously tracks the state of every parking session. To preserve an immutable audit trail, the backend **never permanently deletes a parking log** from Firestore. Instead, it relies on state mutations, temporary tags, and overwrites to resolve edge cases.

### A. Immediate / Temporary Log Creation
*   **`UNIDENTIFIED` (Ghost Car):** Created instantly when the ultrasonic sensor detects a vehicle (`is_occupied: true`) but the camera has not yet sent a successful plate scan. This immediately flags the spot as a violation and summons the "Acknowledge & Resolve" button on the Admin Dashboard.

### B. Mutating / Replacing Pending Logs
*   **Self-Healing Overwrite (Race Condition):** If the camera is delayed by a 5-second OCR retry loop, the ultrasonic sensor will spawn a temporary `UNIDENTIFIED` log. When the camera finally succeeds on its 2nd or 3rd try, the backend detects this pending ghost log and completely **overwrites** it with the real license plate and user data, silently clearing the Admin alarm.
*   **Admin Manual Override:** If the hardware completely fails to read the plate, the Admin must manually intervene by clicking "Acknowledge & Resolve". The backend mutates the pending `UNIDENTIFIED` log by changing its license plate string to `"RESOLVED"` and marking `is_violation = False`.
*   **`ABORTED` (Bouncing Driver):** If a car parks but leaves in under 60 seconds, the backend assumes the driver was just turning around. It closes the session and mutates the license plate field to `"ABORTED"`, preventing any penalties from triggering.
