# ParkMe — Connection Loss Handling

In an IoT environment, wireless connection drops (WiFi stutters, network outages, server reboots) are common. ParkMe employs several hardware and backend strategies to guarantee that no telemetry is lost and that the physical system remains resilient when network connectivity degrades.

---

## 1. Sensor Node (Ultrasonic Spot Detector)

The Sensor Node detects occupancy state changes and communicates with the backend. It has the most critical caching mechanism since it must not lose transition records.

### A. Non-Volatile Storage (NVS) Caching
* **Trigger**: If the WiFi is disconnected, or if the HTTP `POST /api/v1/sensors/heartbeat` request fails (e.g., server timeout or crash) during a state transition (`FREE` <-> `OCCUPIED`), the node flags a publish failure.
* **Action**: The node serializes a `PendingTelemetry` struct:
  ```cpp
  struct PendingTelemetry {
    uint8_t status;          // SpotState (0 = Free, 1 = Occupied)
    int batteryPercent;      // Current battery level
    uint8_t valid;           // Flag indicating cached data exists (0 or 1)
  };
  ```
* **Storage**: This struct is saved directly to the ESP32's onboard **NVS (Non-Volatile Storage)** under the namespace `"pending"` using the ESP32 `Preferences` library. Because it uses physical flash memory, the cached telemetry **survives power losses and reboots**.

### B. Auto-Reconnection Loop
* The sensor node runs `maintainWiFi()` inside its main loop:
  - If `WiFi.status()` is not `WL_CONNECTED`, it automatically attempts to reconnect in the background using `WiFi.setAutoReconnect(true)`.

### C. Offline Telemetry Flush
* Once connection is restored (`WiFi.status() == WL_CONNECTED`):
  - The node executes `flushPendingTelemetry()`.
  - It loads the stored `PendingTelemetry` from NVS and attempts to transmit it to `/api/v1/sensors/heartbeat`.
  - If the server accepts it (HTTP `2xx`), the node marks the state as published and resets the cache by calling `clearPendingTelemetry()`.

*Note:* The backend implements a bulk endpoint (`POST /api/v1/telemetry/bulk`) for chronic batch uploads, but to keep edge memory usage lightweight, the current firmware only persists the latest pending state.

---

## 2. Camera Node (LPR Gate Control)

The Camera Node is responsible for plate scanning and gate relay controls. It focuses on local user feedback and preventing capture loops when offline.

### A. Pre-Scan Connectivity Check
* Before running a scan, the node checks `WiFi.status()`.
* If WiFi is offline, it prints `"WiFi offline", "Cannot scan"` on the physical I2C LCD screen and immediately aborts the scan, returning `ACTION_UNKNOWN`.

### B. 3-Step Retry Loop & Latch Lockout
* If WiFi is online but the HTTP upload fails (e.g. OCR server timeout, socket error), the camera node executes a retry sequence:
  - It attempts up to **3 uploads** total (waiting 1 second between attempts).
  - The LCD updates to show `"Retrying... (1/3)"`, `"Retrying... (2/3)"`, etc.
* **Lockout Protection**: If all 3 retries fail, it stops and prompts the driver with `"Please Clear gate"` on the LCD. 
* **State Latch**: A strict boolean `carPresent` flag prevents it from triggering another scan cycle until the ultrasonic rangefinder detects that the vehicle has completely backed out or cleared the gate threshold (> 20cm). This prevents the camera from endlessly flashing and retrying against a dead backend.

---

## 3. Backend (FastAPI Server) Resilience

The backend is designed to handle hardware communication asymmetries gracefully.

### A. The "Ghost Log" (Camera Offline / Heartbeat Online)
* If the camera node is disconnected/offline, but the sensor node successfully posts an `is_occupied = True` heartbeat, the backend detects that no active parking log exists for that spot.
* It automatically creates a **Ghost Log** in Firestore with `license_plate = "UNIDENTIFIED"` and `is_violation = True` to alert the admin dashboard.

### B. Self-Healing Delayed Camera Payloads
* If the camera node was temporarily delayed due to retries or network stutter, its payload eventually reaches `POST /api/v1/sensors/park`.
* The backend searches for an active `"UNIDENTIFIED"` ghost log for that spot and **overwrites it inline** with the actual OCR plate and updated authorization status. This resolves the anomaly without admin intervention.

---

## 4. Frontend Dashboard

### A. SSE Auto-Reconnection
* The admin panel connects to the backend using Server-Sent Events (SSE) via the `/api/v1/stream` endpoint.
* Modern browser `EventSource` engines natively support auto-reconnection. If the backend drops out, the browser constantly attempts to reconnect. Once the server recovers, the real-time event stream resumes automatically without needing a page refresh.
