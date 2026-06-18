# ParkMe — Hardware Behavior & Edge Cases

The mark of a production-ready IoT system is how it handles physical chaos. This document details the resilience mechanisms built into both the C++ firmware and the Python backend.

---

## 1. Firmware Resilience (ESP32)

### A. Network Disconnection & Caching (Sensor Node)
If the ultrasonic node loses WiFi exactly when a car arrives, the state change is queued in non-volatile storage (NVS) via `queuePendingTelemetry()`. When connectivity restores, `flushPendingTelemetry()` pushes the cached states. Cached data survives power loss.

### B. Adaptive Calibration (Sensor Node)
Holding the boot button (GPIO 0) for 4 seconds triggers a calibration sequence. It samples the exact distance to the concrete floor 15 times, averages it, and computes a baseline minus a 30cm delta (with an 8cm hard floor). This prevents false positives regardless of ceiling height.

### C. Retries & Debouncing (Camera Node)
* **Debouncing:** A strict boolean latch (`carPresent`) prevents the camera from taking multiple pictures of the same car while it's moving through the gate. It only resets when the car fully clears (> 20cm).
* **Retries:** If the OCR fails or network drops, the camera parses the server's `"action": "RETRY"` and will attempt up to 3 captures, displaying a countdown on the LCD.

---

## 2. Backend Edge Cases (FastAPI)

### A. The "Ghost Log" (Hardware-Camera Asymmetry)
**Scenario:** A car parks. The ultrasonic sensor detects it and sends `is_occupied = True`. However, the camera node is broken, blocked, or network-failed, meaning no picture was ever processed.
**Handling:** When the backend receives the ultrasonic heartbeat, it checks if an active log exists. If it doesn't, the backend mathematically deduces the camera failure. It spawns a "Ghost Log" with `license_plate = "UNIDENTIFIED"` and flags it as a violation. This immediately alerts Admins on the dashboard to physically inspect the spot.

### B. Ghost Log Self-Healing
**Scenario:** The camera simply took a long time (retries) and the ultrasonic sensor beat it to the punch, spawning a Ghost Log.
**Handling:** When the camera payload finally arrives, the backend does not create a duplicate log. Instead, it locates the active `UNIDENTIFIED` ghost log and cleanly **overwrites** it with the real license plate and violation status.

### C. Bouncing Driver (Aborted Parking)
**Scenario:** A student parks in a Staff spot, triggering an immediate violation. They realize their mistake and reverse out 15 seconds later.
**Handling:** We do not want to issue parking tickets for three-point turns. When the backend receives the `is_occupied = False` departure event, it checks the duration. If the duration is **under 60 seconds**, the backend wipes the violation flag and overrides the license plate record to `"ABORTED"`.

### D. Duplicate LPR Deduplication
**Scenario:** Bouncing gate frames or rapid camera retries result in identical valid plates being submitted simultaneously.
**Handling:** The backend utilizes an in-memory `cachetools.TTLCache`. If an identical plate is read within a **120-second window**, the request is forcefully dropped with a `duplicate_within_window` reason, saving database read/writes while comfortably covering the 45-second camera retry timeframe without impacting 6-minute heartbeats.
