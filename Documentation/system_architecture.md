# ParkMe — System Architecture & Workflow

ParkMe is a highly secure, event-driven, full-stack IoT system designed to be cloud-native and responsive in real-time.

---

## 1. High-Level Architecture

The system uses an **Edge-Push Architecture** rather than heavy polling.

* **The Edge (ESP32):** The physical hardware acts as the source of truth. Nodes push data to the server only when state changes or during periodic keep-alives.
* **The Brain (FastAPI):** Built on Python and deployed on Google Cloud Run. It receives hardware telemetry, triggers OCR via Google Cloud Vision API, resolves parking logic, writes to Firestore, and pushes events. Timezones are strictly enforced to `Asia/Jerusalem` using `zoneinfo`.
* **The Database (Firestore):** A NoSQL document database providing real-time flexibility and high performance.
* **The Client (Vanilla JS):** The frontend relies on Server-Sent Events (SSE). It opens a persistent stream to the backend, dynamically updating the DOM as events stream in, requiring zero page refreshes.

---

## 2. Event Workflows

### A. The "Park" Event (ESP32-CAM)
1. **Trigger:** The parking spot ultrasonic sensor reports a real `FREE -> OCCUPIED` transition.
2. **Action:** The backend updates Firestore and queues a camera capture command for the mapped `camera_mac`.
3. **Camera Trigger:** The ESP32-CAM listens for an ESP-NOW broadcast from the ultrasonic sensor. Upon receipt, the camera immediately snaps a JPEG (VGA or QVGA depending on PSRAM).
4. **Upload:** The camera sends the image to `POST /api/v1/sensors/park` together with the `camera_mac`.
5. **Processing:** The backend uses Google Cloud Vision to extract the license plate.
6. **Validation:** The backend maps `camera_mac` to a logical spot, looks up the vehicle owner, and checks their Role-Based Access Control (RBAC) permissions against the spot's designated category.
7. **Broadcast:** If allowed, the backend returns `"WELCOME"` and fires an SSE `spot_update` to all connected clients. If denied or unrecognized, it flags a violation.

### B. The "Heartbeat" (ESP32 Ultrasonic)
1. **Trigger:** Every 6 minutes, or immediately upon state change (FREE -> OCCUPIED).
2. **Action:** A lightweight JSON payload is sent to `/api/v1/sensors/heartbeat` with the node's `mac_address`, battery level, and occupancy state.
3. **Database Map:** The backend maps the payload's MAC address against the `sensor_mac` field in the Firestore database to determine the logical spot.

---

## 3. Security & Access Control

* **Identity (JWT):** The frontend uses Firebase Authentication. A secure JWT is passed in the `Authorization` header. The backend verifies this token to determine the user's role (`student`, `lecturer`, `staff`, `admin`).
* **Hardware Auth:** Nodes communicate over raw HTTP/1.1 TCP sockets without additional authentication headers. Security relies on network-level controls.
* **Data Privacy (Need-to-Know Filter):** When a student loads the dashboard, the backend aggressively filters the response. It mathematically drops spots the student has no access to, and strips `license_plate` fields from occupied spots to protect privacy.
* **Stream Security:** The SSE pipeline `/api/v1/stream` routes events exclusively to authorized users. An eavesdropping student physically cannot receive an SSE packet intended for an admin or staff member.
