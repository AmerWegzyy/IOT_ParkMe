# ParkMe API Documentation (Swagger UI Tour)

Here is a complete guided tour of your FastAPI Swagger UI documentation at `http://localhost:8000/docs#/`. FastAPI automatically generates this interactive interface based exactly on the Python code we wrote in `main.py`.

> **Note:** The frontend (Vanilla JS) is served directly by FastAPI via a `StaticFiles` mount, so the same server that handles the API also serves the web UI — no separate web server needed.

---

### 🟢 Part 1: The "default" Dropdowns (Your API Endpoints)

Because we didn't explicitly group our endpoints into custom "tags" (like "Users", "Sensors", etc.), FastAPI groups them all under a single section called **default**. Here are the dropdowns you see, representing every route your server exposes:

#### 1. `GET /api/v1/stream`
* **What it is**: The Server-Sent Events (SSE) pipeline. This is the persistent, one-way tunnel that pipes real-time data from the backend to the frontend.
* **Inside the dropdown**: 
  * **Parameters**: It expects a `token` (string) as a query parameter (e.g., `?token=eyJ...`). 
  * **Responses**: A successful response (`200`) returns `text/event-stream`, which is the live continuous text feed. A `401` means the token was missing or invalid.
  * **Role filtering**: `spot_update` events are filtered by the user's role (e.g., standard drivers only see relevant spots). `log_event` messages are only sent to admin connections.

#### 2. `POST /api/v1/sensors/park`
* **What it is**: The Edge Sensor Fusion endpoint. When the ESP32 camera detects a car entering, it captures a JPEG and fires it here. The backend runs the image through **Google Cloud Vision API** for license-plate recognition (LPR).
* **Inside the dropdown**:
  * **Request Body (multipart/form-data)**: It accepts `camera_mac` (string — the MAC address of the ESP32-CAM camera node) as a text form field and `file` (a binary JPEG upload). The backend dynamically resolves the `spot_id` by querying Firestore for the matching `camera_mac`.
  * **Responses**: A `200 OK` returns a JSON object with `status`, `action`, and `message` keys:
    * **Authorized plate**: `{"status": "ok", "action": "WELCOME", "message": "Welcome, <name>!"}`
    * **Unauthorized plate**: `{"status": "ok", "action": "DENIED", "message": "Not authorized"}`
    * **OCR failure**: `{"status": "failed", "reason": "could_not_read_plate", "action": "RETRY", "message": "Scan again"}`
    * **Duplicate within 5s**: `{"status": "dropped", "reason": "duplicate_within_5s", "action": "RETRY", "message": "Processing..."}`
    * **Invalid spot**: `{"status": "failed", "reason": "invalid_spot_id", "action": "RETRY", "message": "Invalid spot"}`
  * **Behind the scenes**: The endpoint also performs ghost-log self-healing (overwrites stale `UNIDENTIFIED` logs with real plate data) and bouncing-driver detection (if a car leaves within 60 seconds, the session is marked `ABORTED`).

#### 3. `POST /api/v1/sensors/heartbeat`
* **What it is**: The lifeline endpoint for the ESP32. The sensor periodically POSTs its current physical state so the server knows it hasn't died and the battery isn't empty.
* **Inside the dropdown**:
  * **Request Body**: Expects a JSON matching the `HeartbeatPayload` schema (MAC address, occupancy state, battery level).
  * **Responses**: **`202 Accepted`** confirms receipt. This is also where the backend secretly detects "Broken Camera" anomalies — if the heartbeat says "Occupied" but the system has no record of an image being sent!
  * **Spot lookup**: The backend finds the parking spot by querying the `parking_spots` collection for the document whose `sensor_mac` field matches the provided `mac_address`. There is no `spot_id` in this payload.

#### 4. `PUT /api/v1/sensors/resolve`
* **What it is**: The admin tool to fix anomalies. If a camera breaks or gets covered in mud, the system flags the spot as `UNIDENTIFIED`. 
* **Inside the dropdown**:
  * **Parameters**: It requires an `Authorization` header containing the admin's Bearer token.
  * **Request Body**: Expects JSON matching `ResolvePayload` (`spot_id` as a string).
  * **Responses**: `200 OK` confirms the anomaly was manually cleared by the admin. `403` means a standard user tried to hack the endpoint.

#### 5. `GET /api/v1/spots`
* **What it is**: The initialization endpoint for the Vanilla JS frontend map.
* **Inside the dropdown**:
  * **Parameters**: Requires an `Authorization` Bearer token.
  * **Responses**: A `200 OK` returns a JSON array of `spots`. Behind the scenes, the backend uses the token to dynamically filter this array:
    * **Admin users** see all spots, including sensitive fields like `license_plate`, `battery_level`, and `last_seen`.
    * **Standard drivers** only receive spots matching their category (e.g., special-needs) and without the sensitive fields.

#### 6. `GET /api/v1/logs`
* **What it is**: The endpoint that fetches the historical security feed for the admin panel.
* **Inside the dropdown**:
  * **Parameters**: Requires an `Authorization` Bearer token.
  * **Responses**: A `200 OK` returns an array of the 50 most recent security alerts (unauthorized plates or camera failures). `403 Forbidden` triggers if a standard driver tries to peek at the logs.

#### 7. `GET /api/v1/users/me`
* **What it is**: Fetches the authenticated user's profile and role details.
* **Inside the dropdown**:
  * **Parameters**: Requires an `Authorization` Bearer token containing a verified Firebase ID Token.
  * **Responses**: A `200 OK` returns user data: `uid`, `user_id`, `email`, `name`, `role`, `is_special_needs`. `401 Unauthorized` triggers if the Firebase ID Token is invalid or expired.

#### 8. `POST /api/v1/telemetry/bulk`
* **What it is**: A bulk telemetry ingestion endpoint. The ESP32 can batch multiple telemetry events (e.g., cached readings from NVS storage) and send them in one shot.
* **Inside the dropdown**:
  * **Request Body**: Expects a JSON matching the `BulkPayload` schema — an object containing an `events` array of `BulkTelemetryItem` objects.
  * **Responses**: `200 OK` acknowledges receipt. Currently this endpoint logs the events but does not perform advanced processing or storage — it's a forward-looking hook for future analytics.

---

### 📦 Part 2: The "Schemas" Section

At the very bottom of the page, FastAPI lists all the "Schemas". These are the strict data blueprints (Pydantic Models) we defined to ensure the backend only accepts perfectly formatted data. If a client sends data that violates a schema, FastAPI instantly rejects it with a `422 Unprocessable Entity` error before our code even runs.

#### 1. `HeartbeatPayload`
* **What it is**: The strict blueprint for the ESP32's periodic check-in.
* **Inside the dropdown**: You'll see it strictly requires `mac_address` (string), `is_occupied` (boolean: true/false), and `battery_level` (float: 0–100). If the ESP32 forgets to send the battery level, FastAPI rejects it. Note: there is no `spot_id` here — the backend resolves the spot by querying the `parking_spots` collection for the document whose `sensor_mac` field matches the provided `mac_address`.

#### 2. `ResolvePayload`
* **What it is**: The blueprint for the "Acknowledge & Resolve" button click.
* **Inside the dropdown**: Requires exactly one field: `spot_id` (string, e.g. `"444"`). 

#### 3. `LoginPayload`
* **What it is**: The blueprint for user login/registration data.
* **Inside the dropdown**: Contains the fields needed when syncing a Firebase-authenticated user with the local database.

#### 4. `BulkTelemetryItem`
* **What it is**: A single telemetry event inside a bulk upload.
* **Inside the dropdown**: Represents one timestamped reading from a sensor node.

#### 5. `BulkPayload`
* **What it is**: The wrapper for the bulk telemetry endpoint.
* **Inside the dropdown**: Contains an `events` array of `BulkTelemetryItem` objects.

#### 6. `HTTPValidationError` & `ValidationError`
* **What they are**: These aren't schemas we wrote; they are automatically generated by FastAPI.
* **Inside the dropdown**: They describe the exact structure of the error message FastAPI will send back to the client if they violate one of the schemas above (e.g., detailing exactly which field was missing or the wrong data type).
