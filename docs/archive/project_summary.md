
# ParkMe System Summary & Architecture Report

Here is the definitive, unambiguous summary of everything we have built for the ParkMe platform. We have architected a highly secure, event-driven, full-stack IoT system designed to be entirely cloud-deployable. 

### 1. The Core Architecture
Instead of using a heavy, constantly-polling architecture, we implemented **Edge Sensor Fusion** combined with **Server-Sent Events (SSE)**. 
* **The Edge (ESP32)** is the source of truth. It pushes data to the server only when necessary.
* **The Server (FastAPI)** acts as the brain. It receives hardware data, queries Google Cloud Vision API to extract license plates, writes to the Firestore database, and instantly pipes the new data out to active HTTP streams.
* **The Client (Vanilla JS)** maintains a single, open persistent connection to the server. When the server pushes JSON down the pipe, the browser dynamically updates the DOM without ever needing to refresh the page.

### 2. Identity & Role-Based Access Control (RBAC)
We implemented strict Cryptographic Authentication using **Firebase ID Tokens (JWT)**.
* **Users** authenticate directly with Firebase Auth and the frontend fetches their profile via `/api/v1/users/me` to determine their role (`student`, `admin`, `staff`).
* **The "Need-to-Know" Filter**: If a student requests the list of spots (`/api/v1/spots`), the backend mathematically drops all `staff` and `special-needs` spots from the response. Furthermore, if a student spot is occupied, the backend strips the `license_plate` from the JSON entirely to protect privacy, leaving the frontend to just render it as "TAKEN".
* **Admin God-Mode**: Admins bypass all filters. They receive the exact license plates, violation statuses, hardware battery levels, and last-ping timestamps for every spot in the facility.

---

### 3. Handling the "Nasty Cases" (Backend Defenses)
The mark of a production-ready IoT system is how it handles physical chaos. Here is exactly how your backend defends against hardware failures and edge cases:

#### Nasty Case A: The "Broken Camera" or "Muddy License Plate"
**The Scenario:** A car pulls into Spot 444. The ultrasonic sensor correctly tells the server that the spot is physically occupied. However, the camera module is physically broken, or the car's plate is caked in mud, so the `/sensors/park` endpoint never receives an image (or OCR fails to read it).
**The Defense:** The backend relies on the `/sensors/heartbeat` API. If the heartbeat declares `is_occupied = True`, the backend checks the `parking_logs` database. If it realizes that no camera data arrived to open a session, it mathematically deduces an anomaly. It artificially spawns a database log with `license_plate = 'UNIDENTIFIED'` and forcefully flags it as a violation.
**The Resolution:** This triggers an instant SSE broadcast. On the Admin's frontend, the spot flashes red and a button appears. The admin physically walks to the spot, writes down the plate or fixes the camera, and clicks "Acknowledge & Resolve", which sends a `PUT /sensors/resolve` request to normalize the database.

#### Nasty Case B: The "Bouncing Driver" (Drive-throughs)
**The Scenario:** A student pulls into a `staff` spot, triggers the camera, gets flagged as a violation, but immediately realizes their mistake and reverses out of the spot 15 seconds later.
**The Defense:** We don't want to issue parking tickets for executing a three-point turn. When the car leaves, the ESP32 sends an `is_occupied = False` heartbeat. The backend calculates the exact delta between `entry_time` and `now`. If the car was in the spot for **less than 60 seconds**, the backend intercepts the log, wipes the violation status, and actively overrides the license plate string in the database to `'ABORTED'`.

#### Nasty Case C: The "Eavesdropping Hacker"
**The Scenario:** A tech-savvy student opens their browser's Network tab and attempts to listen to the SSE `/stream` to find out exactly when security admins arrive or to track staff license plates.
**The Defense:** The backend maps every single open SSE `asyncio.Queue` connection to the JWT role of the user who opened it. When the backend triggers `await broadcast_event("spot_update", ...)`, the server literally skips the student's network pipe if the update pertains to a staff spot. Security logs are exclusively routed to connections carrying the `admin` role. The student physically cannot receive the packets.


