# Edge Sensor & LPR Synchronization Behavior

This document outlines how the ParkMe IoT backend handles synchronization between the **ultrasonic sensor node** (submitting heartbeats to `/api/v1/sensors/heartbeat`) and the **ESP32-CAM camera node** (submitting plate photos to `/api/v1/sensors/park`). These are **separate physical devices**: the sensor monitors an individual parking spot, while the camera is positioned at the parking-area gate.

All data is stored in **Google Cloud Firestore** (NoSQL). There are no SQL tables — records are documents in the `parking_logs` and `parking_spots` collections.

---

## 1. Normal Vehicle Arrival Flow (Ideal Case)

When a vehicle arrives at a parking spot and the camera transmits data before the heartbeat:

1. **Camera POST Creates the Session (`/api/v1/sensors/park`):**
   - The ESP32-CAM captures the plate image and submits a `multipart/form-data` request containing `spot_id` and the JPEG image.
   - The backend sends the image to the **Google Cloud Vision API** for OCR, identifies the driver and their permits via Firestore, determines violation status, and creates a new parking log document:
     ```python
     db.collection("parking_logs").add({
         "spot_id": spot_id,
         "license_plate": license_plate,
         "user_id": user_id,
         "snapshot_role": snapshot_role,
         "entry_time": server_time,
         "exit_time": None,
         "is_violation": is_violation
     })
     ```
   - The parking spot document is updated (`is_occupied: True`), and the UI broadcasts this state via SSE, showing the spot as occupied with the recognized license plate.

2. **Subsequent Heartbeat Sync:**
   - The sensor node sends its heartbeat payload with `is_occupied: true` to `/api/v1/sensors/heartbeat`.
   - The backend queries Firestore for an active log (a document where `exit_time == None`) for that spot.
   - Because the active log already exists, the fallback logic is bypassed. The heartbeat simply updates telemetry (`last_seen` timestamp and `battery_level`).

---

## 2. Synchronization Anomaly Behaviors

### Scenario A: Sensor heartbeat arrives first, camera upload is delayed (Self-Healing)

This occurs under poor network conditions when the low-bandwidth sensor heartbeat reaches the server faster than the heavy image upload.

1. **Heartbeat Creates a Ghost Log:**
   - The `/api/v1/sensors/heartbeat` endpoint receives `is_occupied: true`.
   - It queries Firestore for an active log for this spot:
     ```python
     logs_ref.where(filter=FieldFilter("spot_id", "==", spot_id))
             .where(filter=FieldFilter("exit_time", "==", None))
     ```
   - Finding none (the camera upload hasn't arrived yet), it initiates the **"Broken Camera" Recovery Flow** and creates an `UNIDENTIFIED` ghost log:
     ```python
     db.collection("parking_logs").add({
         "spot_id": spot_id,
         "license_plate": "UNIDENTIFIED",
         "entry_time": server_time,
         "exit_time": None,
         "is_violation": True,
         "user_id": None,
         "snapshot_role": None
     })
     ```
   - The dashboard updates to show the spot as **Occupied (Red)** with the plate **`UNIDENTIFIED`** and a violation flag.

2. **Delayed Camera POST Triggers Self-Healing:**
   - When the camera payload eventually reaches `/api/v1/sensors/park`, OCR processes the plate.
   - **Before** creating a new log, the backend checks Firestore for an active `UNIDENTIFIED` ghost log on that spot:
     ```python
     logs_ref.where(filter=FieldFilter("spot_id", "==", spot_id))
             .where(filter=FieldFilter("license_plate", "==", "UNIDENTIFIED"))
             .where(filter=FieldFilter("exit_time", "==", None))
     ```
   - If a ghost log is found, the backend **overwrites it in-place** with the real data:
     ```python
     unidentified_doc.reference.update({
         "license_plate": license_plate,
         "user_id": user_id,
         "snapshot_role": snapshot_role,
         "is_violation": is_violation
         # original entry_time is preserved
     })
     ```
   - **Result:** The ghost log is automatically healed — no admin intervention is required. The dashboard updates to show the correct plate, driver, and violation status.

---

### Scenario B: Camera completely fails — admin manual resolution required

This occurs if the camera never submits an image at all (hardware failure, total network loss, or the vehicle bypasses the gate camera).

1. **Ghost Log Persists:**
   - The heartbeat creates the `UNIDENTIFIED` ghost log as described in Scenario A, step 1.
   - Because the camera never sends a POST to `/api/v1/sensors/park`, the self-healing overwrite never triggers. The ghost log remains active with `license_plate: "UNIDENTIFIED"` and `is_violation: True`.

2. **Admin Manual Resolution:**
   - On the web dashboard, the **Acknowledge & Resolve** button is rendered with a **45-second freeze/countdown**. This lock ensures the admin does not manually resolve the spot while the camera node might still be executing its 3 network retries.
   - Once the 45-second cooldown expires, the administrator clicks **Resolve**, which calls `PUT /api/v1/sensors/resolve`.
   - The endpoint queries for active `UNIDENTIFIED` logs on the given spot and updates them:
     ```python
     for log_doc in active_logs_query:
         log_doc.reference.update({
             "is_violation": False,
             "license_plate": "RESOLVED"
         })
     ```
   - **Result:** The violation is cleared, the plate is marked `RESOLVED`, and the dashboard broadcasts the updated state. This is the **only** scenario where admin intervention is needed.

---

### Scenario C: OCR fails or image is corrupted

This occurs if the camera submits a bad image, the vehicle's plate is dirty/blocked, or OCR fails to parse the text.

1. **LPR/Camera Processing Failure:**
   - The `/api/v1/sensors/park` endpoint fails to read the plate and returns early:
     ```python
     if not license_plate:
         return {"status": "failed", "reason": "could_not_read_plate"}
     ```
   - **No parking log document is created.**

2. **Heartbeat Sync & Recovery:**
   - When the next periodic heartbeat from the sensor node arrives at `/api/v1/sensors/heartbeat` with `is_occupied: true`, the backend detects the occupancy state mismatch (spot is occupied physically, but no active log exists in Firestore).
   - The fallback logic inserts a recovery document in `parking_logs` with the plate **`UNIDENTIFIED`** and `is_violation: True`.
   - **Result:** The system guarantees the spot is shown as occupied on the map and alerts security/admins. The admin can then resolve it manually (Scenario B, step 2), or if the camera retries and eventually succeeds, the self-healing logic (Scenario A, step 2) will overwrite the ghost log automatically.

---

### Scenario D: Bouncing driver — exit within 60 seconds

This handles the case where a vehicle briefly occupies a spot and then leaves almost immediately (e.g., a driver pulling in and then changing their mind).

1. **Exit Detected by Heartbeat:**
   - The sensor sends a heartbeat with `is_occupied: false`.
   - The backend finds the active log and computes the duration between `entry_time` and the current server time.

2. **Abort Logic:**
   - If the duration is **less than 60 seconds**, the log is marked as aborted rather than a normal exit:
     ```python
     if duration_seconds < 60:
         update_data["is_violation"] = False
         update_data["license_plate"] = "ABORTED"
     ```
   - The `exit_time` is set regardless, closing the session.
   - **Result:** The brief occupancy is recorded as `ABORTED` with `is_violation: False`, preventing false violation alerts from transient sensor triggers.
