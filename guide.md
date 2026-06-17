# ParkMe Project Guide for AI Agents

Welcome, Agent. You are assisting with the **ParkMe IoT Smart Parking System**. This document provides the critical context, architecture rules, and edge-case behaviors you must understand before modifying any code.

## 1. Project Overview & Tech Stack
ParkMe is an IoT parking management system that detects vehicles, reads license plates via OCR, checks authorization roles, and manages spot occupancy in real-time.

* **Backend:** Python (FastAPI), located in `/Backend`.
* **Database:** Google Cloud Firestore (NoSQL).
* **AI OCR:** Google Cloud Vision API (Server-side processing).
* **Hardware:** C++ running on ESP32 (Sensor Nodes) and ESP32-CAM (Camera Nodes), located in `/ESP32`.
* **Frontend:** Vanilla HTML/JS with Server-Sent Events (SSE) for real-time UI updates, located in `/Frontend`.

## 2. Codebase Structure & Key Files
* `/Backend/main.py`: The core FastAPI server. Handles routing, hardware payloads, OCR processing, database queries, and SSE broadcasting.
* `/Backend/seed_firestore.py`: Wipes and re-seeds the Firestore database cleanly. Use this when testing database logic.
* `/ESP32/ParkMeSensorNode/`: Ultrasonic sensor firmware under the car.
* `/ESP32/ParkMeCameraNode/`: Camera firmware at the gate.
* `/Frontend/app.js`: The admin dashboard logic handling the real-time SSE stream.

## 3. Core Architecture: MAC Address Mapping
**CRITICAL:** Hardware nodes are "dumb". They do **not** know their logical parking spot ID (e.g., "C1").
1. **Sensor Node (`POST /api/v1/sensors/heartbeat`):** Sends a JSON payload containing its `mac_address`.
2. **Camera Node (`POST /api/v1/sensors/park`):** Sends a `multipart/form-data` payload containing a JPEG and its `camera_mac`.
3. **Backend Logic:** The FastAPI server receives the MAC address, queries the `parking_spots` Firestore collection (filtering by `sensor_mac` or `camera_mac`), and dynamically resolves it to the correct `spot_id`.

## 4. Complex Edge Cases & Self-Healing Logic
Do not break or modify these behaviors without explicit user instruction. The physical world is messy, and the backend handles it as follows:

* **Ghost Logs (Camera Lag):** The tiny JSON heartbeat from the Sensor often arrives faster than the heavy JPEG from the Camera. The backend creates a parking log with `license_plate: "UNIDENTIFIED"`. When the camera payload arrives 2 seconds later, the backend finds the open "UNIDENTIFIED" log and patches it in-place with the real license plate.
* **Bouncing Driver (<60s Rule):** If a car arrives and leaves within 60 seconds (calculated using the `entry_time` and `exit_time` of the log), the backend intercepts the departure, marks the plate as `"ABORTED"`, and sets `is_violation: False` so the driver is not penalized for realizing they parked in the wrong spot.
* **LPR Deduplication:** The camera may accidentally send the same picture multiple times due to network stutter. The backend maintains an in-memory `LPR_DEDUP_CACHE`. If the exact same license plate is processed within a 5-second window, the backend drops it and returns a `RETRY` command to pace the hardware.
* **Offline Sensor Recovery (NVS):** If the ESP32 Sensor loses WiFi, it caches its *most recent* state in NVS memory. Upon reconnection, it fires a normal heartbeat with that latest state. (Note: The backend `/api/v1/telemetry/bulk` endpoint exists for full chronological replay, but the current C++ hardware only sends the single latest state via standard heartbeats).
* **Missing Index Crash:** The heartbeat logic requires a specific Firestore Composite Index on the `parking_logs` collection (`spot_id` ASC, `exit_time` ASC, `entry_time` DESC) to calculate durations. If this index is missing, Firestore will throw a `500 FailedPrecondition` error.

## 5. Development Guidelines
* **Virtual Environment:** The backend dependencies are located in `/Backend/venv2`. Always ensure you activate this environment (`source Backend/venv2/bin/activate`) before running Python commands or running the server.
* **Time Zones:** The system enforces Israel Standard Time (`Asia/Jerusalem`). On Windows/WSL, Python requires the `tzdata` package for `zoneinfo` to resolve this correctly.
* **Firestore Overwrites:** Always use the `delete_collection` helper in `seed_firestore.py` to wipe collections before inserting mock data, otherwise Firestore may retain ghost fields.
