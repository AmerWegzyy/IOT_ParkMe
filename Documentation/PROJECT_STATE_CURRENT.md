# Project State (Current, Code-Verified) — 2026-06-24

## 1. Overview
ParkMe is an IoT-based Smart Campus Parking system. The current implementation relies on ESP32-based hardware nodes (Ultrasonic Sensors and Cameras), a Python FastAPI backend, and a Vanilla HTML/JS frontend. The system detects when a vehicle occupies a parking spot, captures an image of the license plate, processes it using Google Cloud Vision for OCR, and verifies the user's role-based access against a Firestore database. If the plate cannot be read, an Admin can manually review the capture and accept/reject the vehicle.

## 2. Architecture
The architecture follows an **Edge-Push** model:
1. **Hardware Detection**: The ESP32 `ParkMeSensorNode` continuously monitors an ultrasonic sensor. If an object is detected within a hardcoded 20cm threshold, the spot is considered occupied.
2. **ESP-NOW Trigger**: The Sensor Node immediately broadcasts an ESP-NOW packet containing its state to the `ParkMeCameraNode`.
3. **Camera Capture**: Upon receiving the ESP-NOW trigger, the Camera Node instantly snaps a JPEG and `POST`s it directly to the backend (`/api/v1/sensors/park`) along with its MAC address. 
4. **Heartbeats & Telemetry**: The Sensor Node also connects to WiFi to send heartbeats (`/api/v1/sensors/heartbeat`). If offline during an event, it caches telemetry and bulk-uploads it later (`/api/v1/telemetry/bulk`).
5. **Backend Processing**: The FastAPI backend receives the image, calls Google Cloud Vision to extract the license plate, maps the camera's MAC address to a logical Spot ID in Firestore, and verifies the plate against the `vehicles` and `users` collections.
6. **Live Frontend Updates**: The backend broadcasts updates via Server-Sent Events (SSE) on `/api/v1/stream`. The Vanilla JS frontend (`app.js`) listens to these events to instantly update the UI without polling.
7. **LCD Displays (Zero-Latency)**: The `ParkMeSensorNode` connects to a dedicated SSE stream (`/api/v1/displays/stream`) to instantly receive and render text commands on the I2C LCD screen without polling delays. Network operations run on a background FreeRTOS core.

## 3. Directory Structure
```text
.
├── Backend/                 # Python/FastAPI server (source of truth for logic)
│   └── main.py              # Core API endpoints and SSE broadcaster
├── Documentation/           # High-level architecture and guides
│   └── PROJECT_STATE_CURRENT.md # This file
├── ESP32/                   # Firmware source code (Arduino/C++)
│   ├── ParkMeCameraNode/    # ESP32-CAM firmware (ESP-NOW receiver, HTTP POSTer)
│   ├── ParkMeSensorNode/    # ESP32 firmware (Ultrasonic, ESP-NOW sender, Telemetry)
│   ├── ParkMeCommon/        # Shared structs and macros (duplicated for ease of build)
│   └── ParkMeLcd/           # Shared LCD abstraction
├── Frontend/                # Web Dashboard (Vanilla HTML/CSS/JS)
└── firebase.json            # Firebase hosting config
```

## 4. File-by-File Breakdown

### Backend/main.py
- **Purpose**: Core FastAPI application serving API endpoints, handling Firebase integration, and broadcasting SSE.
- **Key contents**:
  - `receive_heartbeat_data` & `receive_bulk_data`: Resolves spots by MAC and updates Firestore.
  - `receive_park_event`: Extracts plates via Google Vision OCR. Contains logic for "Ghost Logs" (unidentified plates) requiring admin review.
  - `stream_events` & `stream_display_events`: Manages SSE clients for the web frontend and hardware displays.
  - `poll_display_command_endpoint` & `complete_display_result`: Manages in-memory LCD message queues and acknowledgments.
  - `get_capture`: Serves `/api/v1/captures/{spot_id}` which dynamically decodes Base64 images directly from Firestore.
- **Depends on**: `google-cloud-vision`, `firebase-admin`, `fastapi`, `cachetools`.

### Backend/parking_logic.py
- **Purpose**: Pure Python datetime helper functions.
- **Key contents**: `should_preserve_recent_active_log` (used to prevent heartbeats from overwriting camera logs if they arrive out-of-order).

### Backend/seed_firestore.py & create_auth_users.py
- **Purpose**: Utility scripts to populate Firestore (`parking_spots`, `vehicles`) and Firebase Auth.

### Frontend/app.js, index.html, style.css
- **Purpose**: Vanilla web dashboard for Admins and Users.
- **Key contents**:
  - Firebase Auth integration via compat SDKs.
  - Subscribes to `/api/v1/stream` via `EventSource`.
  - Dynamic spot cards, Admin Security Logs, and Admin manual Accept/Reject buttons.

### ESP32/ParkMeSensorNode/ParkMeSensorNode.ino
- **Purpose**: Monitors the ultrasonic sensor and maintains network connectivity using a FreeRTOS dual-core architecture.
- **Key contents**: 
  - **Core 1 (Main Loop)**: Handles ultrasonic sampling (20cm threshold), ESP-NOW broadcasts, and OLED display rendering without blocking.
  - **Core 0 (Network Task)**: Maintains WiFi, connects to the SSE display stream, and uploads HTTP JSON telemetry in the background. Caches offline states.

### ESP32/ParkMeCameraNode/ParkMeCameraNode.ino
- **Purpose**: Listens for ESP-NOW triggers and uploads photos.
- **Key contents**: `handleEspNowSensorStateReceived()` triggers capture without validating the incoming Spot ID. Uploads multipart/form-data to `/api/v1/sensors/park`.

### ESP32/SECRETS.example.h
- **Purpose**: Template for API keys, WiFi credentials, and hardcoded variables.

## 5. External Integrations
- **Firebase Auth**: Used by the frontend for user login. Backend verifies JWT tokens.
- **Firestore**: Source of truth for `parking_spots`, `parking_logs`, `users`, `vehicles`, and `spot_captures`.
- **Google Cloud Vision API**: Backend uses `ImageAnnotatorClient.text_detection` and `document_text_detection` for License Plate Recognition.

## 6. Project Health Note
All unused Flutter code, deprecated Camera polling endpoints, local image storage, and legacy documentation have been actively purged from this repository. The architecture described above accurately reflects 100% of the active codebase.

## 7. Edge Case Handling
1. **Network / Wi-Fi Loss**:
   - If the `ParkMeSensorNode` loses connection to the backend, it continues monitoring the spot locally.
   - It caches the telemetry (entry/exit timestamps and occupancy state) in its local memory.
   - Once the connection is restored, it bulk-uploads all missed events to the `/api/v1/telemetry/bulk` endpoint so the backend history is perfectly maintained.
2. **"Bouncy Driver" (Parking Adjustments)**:
   - When a car parks, the driver might adjust their position, momentarily triggering the sensor as "free" and then "occupied" again.
   - The backend uses a 90-second "bouncy driver" window (`BOUNCY_DRIVER_MAX_SECONDS`). If the car briefly vacates the spot but returns within 90 seconds, the backend ignores the momentary exit and merges the events to prevent logging duplicate parking sessions.
3. **Unrecognized License Plates (OCR Failure)**:
   - If the Google Cloud Vision API completely fails to read the license plate from the camera's image, the backend creates a "Ghost Log" (recording the plate as `UNIDENTIFIED`).
   - The raw image from the camera is saved directly into the `spot_captures` Firestore collection as a Base64 string.
   - The Admin Dashboard immediately displays this captured image directly inside the live Spot Card for that parking spot, along with two manual action buttons: **Accept Vehicle** and **Reject Vehicle**.
   - Clicking these buttons manually forces the system to either authorize or reject the vehicle, resolving the Ghost Log. If rejected, the image is permanently transferred to the parking log as violation evidence.

4. **Violation Image Capture & Evidence**:
   - When a vehicle parks and is flagged as a violation (either because its recognized plate is unregistered, or an Admin manually clicks "Reject Vehicle"), the system permanently stores the base64-encoded camera capture directly in the `parking_logs` document (`capture_base64`).
   - The Admin Security Logs instantly render a **"Show Picture"** button in realtime next to the violation entry, allowing the admin to view the exact frame that caused the violation without refreshing the page.
   - **Bouncy Driver Reversion**: If the violation was actually triggered by a "bouncy driver" who immediately leaves the spot within the 90-second grace period, the backend broadcasts a `log_aborted` SSE event. The frontend dynamically intercepts this, updates the live log text to "Driver aborted parking", and automatically removes the "Show Picture" button to keep the dashboard clean.

## 8. Concrete System Timings & Thresholds
- **Ultrasonic Trigger Threshold**: `20.0f` cm (Distance under 20cm instantly triggers the ESP-NOW broadcast to the camera).
- **Sensor Heartbeat Period**: `20` seconds (The sensor pings the server via HTTP every 20 seconds while occupied to confirm the vehicle is still present).
- **Bouncy Driver Grace Period**: `90` seconds (Time allowed for a driver to adjust their car without closing the active parking log).
- **Camera First Heartbeat Grace Period**: `10` seconds. 
  - **The Race Condition**: Because the Camera is triggered instantly by ESP-NOW, its picture upload might arrive at the server *before* the Sensor's HTTP heartbeat. Both devices send HTTP requests simultaneously over Wi-Fi when a car parks.
  - **The Solution**: If the backend receives a Sensor heartbeat claiming a spot *just* became occupied, but the Camera already created a log for that spot less than 10 seconds ago, the backend understands this is the same physical event. It safely merges the data without accidentally overwriting the license plate or creating a duplicate parking session.
- **Manual Review UI Timeout**: `30` seconds (If a Ghost Log is created but the camera image takes too long to upload, the frontend allows the Admin to make a blind Accept/Reject decision after 30 seconds).
- **Display Manual Review Hold**: `8` seconds (When an admin manually resolves a spot, the LCD display will hold the confirmation message, e.g., "Admin cleared", for 8000 milliseconds).

## 9. Database Structure
The backend relies entirely on Firestore as the central source of truth. The database is composed of the following collections:

1. **`parking_spots`** (Document ID: `spot_id`, e.g., `A1`)
   - **Fields**: `sensor_mac`, `camera_mac`, `category`, `is_occupied`, `battery_level`, `last_seen`, `license_plate`, `is_violation`, etc.
   - **Purpose**: Stores the realtime state and configuration of every physical parking spot.

2. **`users`** (Document ID: `email`)
   - **Fields**: `name`, `email`, `role`, `created_at`.
   - **Purpose**: Tracks user accounts and their authorization roles (e.g., `admin`, `student`, `lecturer`).

3. **`vehicles`** (Document ID: `license_plate`)
   - **Fields**: `license_plate`, `user_id` (email), `created_at`.
   - **Purpose**: Maps a physical license plate string to the registered user. Used for access verification.

4. **`parking_logs`** (Document ID: Auto-generated)
   - **Fields**: `spot_id`, `license_plate`, `user_id`, `snapshot_role`, `entry_time`, `exit_time`, `is_violation`, `capture_base64`.
   - **Purpose**: Maintains the historical log of all parking events. As of recent features, confirmed violations directly include the encoded image in `capture_base64` for realtime frontend display.

5. **`spot_captures`** (Document ID: `spot_id`)
   - **Fields**: `image_base64`.
   - **Purpose**: Temporarily holds the Base64 representation of a camera capture strictly during the manual review phase for `UNIDENTIFIED` plates.

## 10. LCD Display Messaging Flow
The LCD display provides real-time feedback to the driver by coordinating messages instantly from the local ESP-NOW network and asynchronously from the backend server.

**1. Instant Local Hardware Updates (Via ESP-NOW)**
Because the sensor triggers the camera instantly, the camera board communicates its progress back to the sensor board's LCD via local wireless (ESP-NOW), providing immediate feedback before the backend is even involved:
- **"Taking photo" / "Please hold"**: The camera has been triggered and is actively capturing the image.
- **"Photo sent" / "Checking plate"**: The image capture was successful and is being uploaded to the server.
- **"Photo failed" / "Check dashboard"**: The camera failed to capture the image locally.

**2. Backend Server Updates (Via SSE Stream)**
As the backend processes the image and runs the Google Vision OCR, it queues commands in memory and pushes them instantly via the `/api/v1/displays/stream` SSE endpoint to the ESP32's background network task:
- **"Scanning" / "Please wait"**: Displayed during the initial server processing window while OCR and Firestore checks are running.
- **"Welcome [Driver Name]"**: Displayed if the plate is successfully recognized and the user is authorized.
- **"Access denied" / "Please remove car"**: Displayed if the plate is recognized but belongs to an unauthorized/unregistered user (Violation).
- **"Admin review" / "Check dashboard"**: Displayed if the OCR fails to read the plate and the backend routes the log to an Admin for manual Accept/Reject.

## 11. API Endpoints Documentation
The backend exposes a FastAPI REST architecture. Below is the comprehensive list of all active endpoints, the two communicating sides, and their use cases:

### Hardware-to-Backend Endpoints
- **`POST /api/v1/sensors/heartbeat`**:
  - **Caller**: `ParkMeSensorNode` (ESP32) -> Backend
  - **Use Case**: Sent every 20 seconds while a spot is occupied to confirm the vehicle hasn't left. Also reports the battery level.
- **`POST /api/v1/sensors/park`**:
  - **Caller**: `ParkMeCameraNode` (ESP32-CAM) -> Backend
  - **Use Case**: Sent the instant the camera captures an image. Contains the raw multipart/form-data JPEG for Google Vision OCR processing.
- **`POST /api/v1/telemetry/bulk`**:
  - **Caller**: `ParkMeSensorNode` (ESP32) -> Backend
  - **Use Case**: Used to flush offline-cached sensor events (timestamps and occupancy states) back to the server once the ESP32 regains Wi-Fi connection.
- **`GET /api/v1/displays/stream`**:
  - **Caller**: `ParkMeSensorNode` (ESP32) -> Backend
  - **Use Case**: Establishes a real-time SSE stream where the backend pushes display commands directly to the ESP32 with zero latency.
- **`POST /api/v1/displays/poll`**:
  - **Caller**: `ParkMeSensorNode` (ESP32) -> Backend
  - **Use Case**: Acts as a fallback mechanism. The node polls this endpoint to fetch in-memory queued text commands if the SSE stream disconnects.
- **`POST /api/v1/displays/result`**:
  - **Caller**: `ParkMeSensorNode` (ESP32) -> Backend
  - **Use Case**: Sent by the ESP32's background network task immediately after the ESP32 successfully renders an LCD command, acknowledging it.

### Frontend-to-Backend Endpoints
- **`GET /api/v1/stream`**:
  - **Caller**: Frontend (`app.js`) -> Backend
  - **Use Case**: Establishes a persistent Server-Sent Events (SSE) connection so the dashboard receives real-time spot updates, log events, and aborted logs without long-polling.
- **`GET /api/v1/users/me`**:
  - **Caller**: Frontend (`app.js`) -> Backend
  - **Use Case**: Validates the Firebase Auth JWT and returns the user's role (Admin, Student, Lecturer) and points.
- **`GET /api/v1/spots`**:
  - **Caller**: Frontend (`app.js`) -> Backend
  - **Use Case**: Fetches the initial state of all parking spots (occupied, free, violations, battery) when the dashboard first loads.
- **`GET /api/v1/logs`**:
  - **Caller**: Frontend (`app.js`) -> Backend
  - **Use Case**: Admin dashboard requests historical parking logs, filtered for security events.
- **`GET /api/v1/admin/usage-stats`**:
  - **Caller**: Frontend (`app.js`) -> Backend
  - **Use Case**: Admin dashboard requests aggregated usage analytics for the charting interface.
- **`GET /api/v1/captures/{spot_id}`**:
  - **Caller**: Frontend (`app.js`) -> Backend
  - **Use Case**: Renders the temporary base64 image (from `spot_captures`) inside the Spot Card during the live Admin manual review phase.
- **`GET /api/v1/logs/{log_id}/capture`**:
  - **Caller**: Frontend (`app.js`) -> Backend
  - **Use Case**: Renders the permanently saved base64 violation evidence image when the Admin clicks the "Show Picture" button in the Security Logs.
- **`PUT /api/v1/sensors/accept`**:
  - **Caller**: Frontend (`app.js`) -> Backend
  - **Use Case**: Admin clicks "Accept Vehicle". Resolves an `UNIDENTIFIED` plate Ghost Log into a valid, authorized session.
- **`PUT /api/v1/sensors/reject`**:
  - **Caller**: Frontend (`app.js`) -> Backend
  - **Use Case**: Admin clicks "Reject Vehicle". Resolves an `UNIDENTIFIED` plate Ghost Log into a violation log, permanently saving the evidence image.
