# ParkMe API Documentation (Swagger UI Tour)

Here is a complete guided tour of your FastAPI Swagger UI documentation at `http://localhost:8000/docs#/`. FastAPI automatically generates this interactive interface based exactly on the Python code we wrote in `main.py`.

---

### 🟢 Part 1: The "default" Dropdowns (Your API Endpoints)

Because we didn't explicitly group our endpoints into custom "tags" (like "Users", "Sensors", etc.), FastAPI groups them all under a single section called **default**. Here are the dropdowns you see, representing every route your server exposes:

#### 1. `GET /api/v1/stream`
* **What it is**: The Server-Sent Events (SSE) pipeline. This is the persistent, one-way tunnel that pipes real-time data from the backend to the frontend.
* **Inside the dropdown**: 
  * **Parameters**: It expects a `token` (string) as a query parameter (e.g., `?token=eyJ...`). 
  * **Responses**: A successful response (`200`) returns `text/event-stream`, which is the live continuous text feed. A `401` means the token was missing or invalid.

#### 2. `POST /api/v1/sensors/park`
* **What it is**: The Edge Sensor Fusion endpoint. When the ESP32 camera detects a car entering or leaving, it captures an image and fires it here.
* **Inside the dropdown**:
  * **Request Body (multipart/form-data)**: It accepts `spot_id` (integer) and `image` (a binary file/JPEG).
  * **Responses**: A `200 OK` returns a JSON confirmation of the detected license plate and whether the user is authorized.

#### 3. `POST /api/v1/sensors/heartbeat`
* **What it is**: The lifeline endpoint for the ESP32. The sensor periodically POSTs its current physical state so the server knows it hasn't died and the battery isn't empty.
* **Inside the dropdown**:
  * **Request Body**: Expects a JSON matching the `HeartbeatPayload` schema (MAC address, occupancy state, battery level).
  * **Responses**: `200 OK` confirms receipt. This is also where the backend secretly detects "Broken Camera" anomalies if the heartbeat says "Occupied" but the system has no record of an image being sent!

#### 4. `PUT /api/v1/sensors/resolve`
* **What it is**: The admin tool to fix anomalies. If a camera breaks or gets covered in mud, the system flags the spot as `UNIDENTIFIED`. 
* **Inside the dropdown**:
  * **Parameters**: It requires an `Authorization` header containing the admin's Bearer token.
  * **Request Body**: Expects JSON matching `ResolvePayload` (just the `spot_id`).
  * **Responses**: `200 OK` confirms the anomaly was manually cleared by the admin. `403` means a standard user tried to hack the endpoint.

#### 5. `GET /api/v1/spots`
* **What it is**: The initialization endpoint for the Vanilla JS frontend map.
* **Inside the dropdown**:
  * **Parameters**: Requires an `Authorization` Bearer token.
  * **Responses**: A `200 OK` returns a JSON array of `spots`. Behind the scenes, the backend uses the token to dynamically filter this array so standard drivers only receive data about spots that match their specific role.

#### 6. `GET /api/v1/logs`
* **What it is**: The endpoint that fetches the historical security feed for the admin panel.
* **Inside the dropdown**:
  * **Parameters**: Requires an `Authorization` Bearer token.
  * **Responses**: A `200 OK` returns an array of the 50 most recent security alerts (unauthorized plates or camera failures). `403 Forbidden` triggers if a standard driver tries to peek at the logs.

#### 7. `POST /api/v1/auth/login`
* **What it is**: The gateway. Users submit their credentials here to get their cryptographically signed JWT.
* **Inside the dropdown**:
  * **Request Body**: JSON matching the `LoginPayload` (email and password).
  * **Responses**: `200 OK` grants the JSON token (`{"access_token": "ey...", "token_type": "bearer"}`). `401 Unauthorized` means the email doesn't exist.

---

### 📦 Part 2: The "Schemas" Section

At the very bottom of the page, FastAPI lists all the "Schemas". These are the strict data blueprints (Pydantic Models) we defined to ensure the backend only accepts perfectly formatted data. If a client sends data that violates a schema, FastAPI instantly rejects it with a `422 Unprocessable Entity` error before our code even runs.

#### 1. `HeartbeatPayload`
* **What it is**: The strict blueprint for the ESP32's periodic check-in.
* **Inside the dropdown**: You'll see it strictly requires `mac_address` (string), `is_occupied` (boolean: true/false), and `battery_level` (integer: 0-100). If the ESP32 forgets to send the battery level, FastAPI rejects it.

#### 2. `LoginPayload`
* **What it is**: The blueprint for the login form.
* **Inside the dropdown**: Requires `email` (string) and `password` (string). 

#### 3. `ResolvePayload`
* **What it is**: The blueprint for the "Acknowledge & Resolve" button click.
* **Inside the dropdown**: Requires exactly one field: `spot_id` (integer). 

#### 4. `HTTPValidationError` & `ValidationError`
* **What they are**: These aren't schemas we wrote; they are automatically generated by FastAPI.
* **Inside the dropdown**: They describe the exact structure of the error message FastAPI will send back to the client if they violate one of the three schemas above (e.g., detailing exactly which field was missing or the wrong data type).
