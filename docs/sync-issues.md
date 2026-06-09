# Edge Sensor & LPR Synchronization Behavior

This document outlines how the ParkMe IoT backend handles synchronization between physical geomagnetic loop/ultrasonic sensors (submitting heartbeats) and the ESP32-CAM (submitting plate photos).

---

## 1. Normal Vehicle Arrival Flow (Ideal Case)

When a vehicle arrives at a parking spot and the camera transmits data before the heartbeat:
1. **Camera POST Creates the Session (`/sensors/park`):**
   - The ESP32-CAM captures the plate image and submits a `multipart/form-data` request containing `spot_id` and the JPEG image.
   - The backend runs OCR, identifies the driver/permits, updates the database spot status (`is_occupied = TRUE`), and inserts a new session entry into `parking_logs`.
   - The UI broadcasts this state, showing the spot as occupied with the recognized license plate.
2. **Subsequent Heartbeat Sync:**
   - The sensor node sends its heartbeat payload with `is_occupied: true` to `/api/v1/sensors/heartbeat`.
   - The sync logic queries the database and finds the active log created by the camera.
   - Because the active log is already present, the fallback logic is bypassed. The heartbeat simply updates the telemetry (`last_seen` timestamp and battery levels).

---

## 2. Synchronization Anomaly Behaviors

### Scenario A: Sensor sends `is_occupied = true` first, but the camera upload is delayed
This occurs under poor network conditions when the low-bandwidth sensor heartbeat reaches the server faster than the heavy image upload.

1. **Heartbeat Processing:**
   - The `/api/v1/sensors/heartbeat` endpoint receives `is_occupied: true` via JSON.
   - It queries the database for an active log session (`exit_time IS NULL`).
   - Finding none (since the camera upload hasn't registered yet), it initiates the **"Broken Camera" Recovery Flow** (fallback logic):
     ```sql
     INSERT INTO parking_logs (spot_id, license_plate, entry_time, is_violation) 
     VALUES (:spot_id, 'UNIDENTIFIED', :now, TRUE);
     ```
   - The spot status updates on the dashboard to **Occupied (Red)** with the plate **`UNIDENTIFIED`** and flags a violation.

2. **Delayed Camera POST Arrival:**
   - When the camera payload eventually reaches `/api/v1/sensors/park`, LPR processes the plate and registers a new active log.
   - **Resolution:** An administrator can click **Resolve** on the dashboard, which calls `/api/v1/sensors/resolve` to clean up the outstanding `UNIDENTIFIED` log (setting its plate to `'RESOLVED'` and clearing the violation status).

---

### Scenario B: Sensor sends `is_occupied = true`, but the camera upload is corrupted or OCR fails
This occurs if the camera submits a bad image, the vehicle's plate is dirty/blocked, or OCR fails to parse the text.

1. **LPR/Camera Processing Failure:**
   - The `/api/v1/sensors/park` endpoint fails to read the plate and executes the early termination check:
     ```python
     if not license_plate:
         return {"status": "failed", "reason": "could_not_read_plate"}
     ```
   - The request exits with a failure message. **No database transaction or log is created.**

2. **Heartbeat Sync & Recovery:**
   - When the next periodic heartbeat from the node arrives at `/api/v1/sensors/heartbeat` with `is_occupied: true`, the sync logic detects the occupancy state mismatch (spot is occupied physically, but no active log transaction exists).
   - The fallback logic inserts a recovery record in `parking_logs` with the plate **`UNIDENTIFIED`** and `is_violation = TRUE`.
   - **Result:** The system guarantees the spot is shown as occupied on the map, and alerts security/admins that an unidentified vehicle is parked.
