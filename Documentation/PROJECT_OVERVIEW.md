# ParkMe — Complete Project Overview

> **The single source of truth for the ParkMe system.** Verified against the actual code on branch `camera_buffer_fix_branch` (July 2026). This document supersedes the older `PROJECT_STATE_CURRENT.md`, `development-summary.md`, `system_q_and_a.md`, `qa-minimizing-delays.md`, `deployment-todo.md`, and `common-commands.md`.

---

## 1. What ParkMe Is

ParkMe is an IoT Smart Campus Parking system (ICST / Technion). Each parking spot is monitored by ESP32-based hardware: an ultrasonic **Sensor Node** detects when a car arrives, and an ESP32-CAM **Camera Node** photographs the license plate. A Python **FastAPI backend** runs OCR via Google Cloud Vision, checks the plate against registered users in **Firestore**, and pushes live updates to a vanilla HTML/JS **web dashboard** and to a physical **OLED display** at the spot. Unreadable plates go to a manual Admin review flow with photo evidence.

### Technology Stack

| Layer | Technology |
|---|---|
| Edge hardware | ESP32 Dev Module (sensor + OLED), AI-Thinker ESP32-CAM (camera), HC-SR04 ultrasonic, SSD1306 I2C OLED |
| Edge communication | ESP-NOW (board-to-board), WiFi + HTTP/HTTPS (to backend), SSE (backend to display) |
| Backend | Python 3.11, FastAPI, Uvicorn, deployed on Google Cloud Run (region `me-west1`) |
| Database | Firebase Firestore (sole source of truth; no SQL, no local storage) |
| Auth | Firebase Authentication (frontend login → JWT verified by backend) |
| OCR | Google Cloud Vision API (`text_detection` + `document_text_detection`) |
| Frontend | Vanilla HTML/CSS/JS, Firebase compat SDKs, Server-Sent Events; hosted via Firebase Hosting or served by FastAPI |

### Repository Layout

```text
.
├── Backend/                  # FastAPI server
│   ├── main.py               # All API endpoints, SSE broadcasters, business logic (~1600 lines)
│   ├── parking_logic.py      # Pure datetime helpers (unit-testable, no Firebase deps)
│   ├── seed_firestore.py     # Wipes & seeds parking_spots, users, vehicles
│   ├── create_auth_users.py  # Creates the matching Firebase Auth accounts
│   ├── run_local_backend.ps1 # One-click local run (creates .venv, installs, starts uvicorn)
│   ├── Dockerfile            # Cloud Run container
│   └── cloudbuild.yaml       # CI/CD pipeline (build → push → deploy to Cloud Run)
├── Frontend/                 # Web dashboard (index.html, app.js, style.css)
├── ESP32/
│   ├── ParkMeSensorNode/     # Ultrasonic + OLED + ESP-NOW sender + telemetry (dual-core FreeRTOS)
│   ├── ParkMeCameraNode/     # ESP32-CAM: ESP-NOW receiver, capture + upload
│   ├── ParkMeCommon/         # Shared structs, enums, JSON/MAC/HTTP helpers (header-only)
│   ├── ParkMeLcd/            # Legacy I2C LCD driver (superseded by OLED code in sensor node)
│   ├── ScreenProbe/          # I2C bus diagnostic sketch
│   ├── SECRETS.example.h     # Template → copy to SECRETS.h (never commit SECRETS.h)
│   └── hardware-upload-guide.md  # How to flash both boards
├── Unit Tests/               # Hardware validation sketches (ultrasonic, camera, OLED)
├── tests/                    # Python unit tests
├── Documentation/            # This file
└── firebase.json             # Firebase Hosting config (public dir: Frontend)
```

---

## 2. End-to-End Architecture (Edge-Push Model)

```text
 Car arrives
     │
     ▼
 [Sensor Node]──ESP-NOW trigger──▶[Camera Node]
     │                                 │
     │ HTTP heartbeat                  │ HTTP multipart JPEG (1 photo, up to 3 send attempts)
     ▼                                 ▼
 POST /api/v1/sensors/heartbeat   POST /api/v1/sensors/park
     └───────────────┬─────────────────┘
                     ▼
              [FastAPI Backend] ──▶ Google Vision OCR ──▶ Firestore lookup (vehicles → users)
                     │
        ┌────────────┼──────────────────┐
        ▼            ▼                  ▼
   Firestore     SSE /api/v1/stream   SSE /api/v1/displays/stream
   (write logs   (web dashboard,      (OLED on sensor node:
    & spot state) role-filtered)       "Welcome X" / "Access denied")
```

**The full happy-path sequence:**

1. Sensor Node samples the HC-SR04 every 500 ms (3 pulses averaged, 120 ms apart). Distance ≤ the node's calibrated threshold (default 20 cm) ⇒ `OCCUPIED`.
2. On a state change it instantly sends an ESP-NOW `SensorStateMessage` — both directly to the configured camera MAC and as a broadcast fallback — and flags a heartbeat for the network task.
3. Camera Node receives the trigger, ACKs over ESP-NOW (driving instant local OLED feedback), flushes **two** stale frames from the camera FIFO, captures **one** fresh JPEG, and uploads it as multipart form data to `/api/v1/sensors/park`. If the upload fails it re-sends **the same frame** up to 3 times total (no re-capture).
4. Backend maps `camera_mac` → spot document, runs OCR and validates the result as a plausible Israeli plate (contiguous digit groups, exactly 7–8 digits — noise like permit stickers or phone numbers is never merged into a phantom plate), looks up the plate in `vehicles` → `users`, and decides:
   - registered user whose role matches the spot category (or admin) ⇒ **WELCOME**
   - unregistered plate or role mismatch ⇒ **DENIED** (violation, photo saved as evidence)
   - OCR failed ⇒ **Ghost Log / manual admin review** (see §5)
5. Backend writes/updates `parking_logs` and `parking_spots`, then pushes a `spot_update` SSE event to dashboards and a display command ("Welcome NAME" / "Access denied") to the spot's OLED.
6. When the car leaves, the sensor heartbeat with `is_occupied=false` closes the log (`exit_time`), clears review state, and deletes any temporary capture.

---

## 3. The Backend (`Backend/main.py`)

### 3.1 API Endpoints

**Hardware → Backend**

| Endpoint | Caller | Purpose |
|---|---|---|
| `POST /api/v1/sensors/heartbeat` | Sensor Node | State + battery every 20 s while occupied (and on every state change). Body: `{mac_address, is_occupied, battery_level}`. |
| `POST /api/v1/sensors/park` | Camera Node | Multipart upload: `camera_mac` field + JPEG `file`. Triggers OCR + authorization decision. Returns a gate response (`action: WELCOME/DENIED`, `message`, …). |
| `POST /api/v1/telemetry/bulk` | (Sensor Node, offline replay) | Replays cached `{t, v}` occupancy events in timestamp order. **Note:** current firmware does not call this — it persists only the single latest unsent state in NVS and flushes that (see §6.4). |
| `GET /api/v1/displays/stream?display_id=…` | Sensor Node (Core 0) | SSE stream of display commands; server sends `: keepalive` comments every 15 s. |
| `POST /api/v1/displays/poll` | Sensor Node | Fallback polling (750 ms) when SSE is down; pops the queued command from the in-memory store. |
| `POST /api/v1/displays/result` | Sensor Node | ACK that a command was rendered (`request_id`, `DISPLAYED`/`FAILED`). Logged only. |

**Frontend → Backend** (all require `Authorization: Bearer <Firebase JWT>` except the SSE stream which takes `?token=`)

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/users/me` | Verifies the JWT, returns `{user_id, name, role, is_special_needs}` from the `users` collection. |
| `GET /api/v1/spots` | Initial spot list. Admins see everything (plates, violations, battery, review state); other roles only see spots of their own category, with plates hidden. |
| `GET /api/v1/stream?token=…` | SSE: `spot_update`, `log_event`, `log_aborted`. Admins get all events; non-admins only get `spot_update` for their category. |
| `GET /api/v1/logs` | Admin only. Last 50 logs, filtered to anomalies only (violations / unidentified / resolved / aborted / manual decisions). Normal authorized parking is excluded by design. |
| `GET /api/v1/admin/usage-stats` | Admin only. Aggregates: occupancy, session counts by outcome, peak hour, busiest spot, average duration. |
| `GET /api/v1/captures/{spot_id}` | Decodes the temporary review image from `spot_captures` (base64 → JPEG response, no-cache headers). |
| `GET /api/v1/logs/{log_id}/capture` | Decodes the permanent violation evidence from `parking_logs.capture_base64`. |
| `PUT /api/v1/sensors/accept` | Admin resolves a Ghost Log as authorized (`license_plate` → `MANUAL_ACCEPTED`). |
| `PUT /api/v1/sensors/reject` | Admin resolves a Ghost Log as violation (`license_plate` → `REJECTED`); copies the review image into the log as permanent evidence. |

The backend also mounts `Frontend/` as static files at `/`, so one local server serves both API and dashboard.

### 3.2 The Sentinel-Plate State Machine

The active parking log's `license_plate` field doubles as the spot's workflow state. `build_effective_spot_state()` translates these sentinels into what clients see:

| Sentinel value | Meaning | Effective UI state |
|---|---|---|
| `UNIDENTIFIED` | OCR failed (or heartbeat arrived before any photo); awaiting camera image and/or admin review | Occupied, violation styling, review panel with Accept/Reject |
| `MANUAL_ACCEPTED` | Admin clicked Accept | Occupied, authorized ("ADMIN ACCEPTED") |
| `REJECTED` | Admin clicked Reject | Occupied, violation ("REJECTED"), evidence photo shown; LCD repeats "Access denied / Please remove car" on each heartbeat |
| `RESOLVED` | Legacy resolved marker | Rendered as free/empty |
| `ABORTED` | Car left within the 90 s bouncy-driver window | Log rewritten to "Driver aborted parking", violation flag cleared |
| *(real plate digits)* | Normal recognized session | Occupied; violation flag depends on authorization result |

The camera-upload endpoint checks the active log's sentinel **before** running OCR, so a photo that arrives after an admin has already decided (accepted/rejected/resolved) cannot overwrite the decision — it returns the corresponding gate response instead.

### 3.3 Race Conditions & Edge Cases (all implemented in code)

- **Camera beats heartbeat (10 s grace):** ESP-NOW makes the camera upload often arrive before the sensor's HTTP heartbeat. When a heartbeat reports a *new* arrival but an active log already exists, `should_preserve_recent_active_log()` (in `parking_logic.py`) keeps that log if it is < 10 s old (`CAMERA_FIRST_HEARTBEAT_GRACE_SECONDS`), is not a terminal sentinel, and started after the spot's `last_seen`. Otherwise the stale log is closed and a fresh `UNIDENTIFIED` log is created.
- **Bouncy driver (90 s):** If a car exits less than 90 s (`BOUNCY_DRIVER_MAX_SECONDS`) after entry and the log isn't a terminal sentinel, the exit converts the log to `ABORTED`, clears `is_violation`, and broadcasts `log_aborted` so the dashboard rewrites the log line and removes the "Show Picture" button. The `capture_base64` (if any) is intentionally *not* deleted — it stays archived in the log.
- **Missing photo (30 s review deadline):** When a Ghost Log exists, `review_resolve_after = review_started_at + 30 s` (`CAMERA_UPLOAD_GRACE_SECONDS`). Review status progresses `awaiting_capture` → `photo_review` (image arrived) or `missing_photo` (deadline passed with no image). The frontend disables Accept/Reject until an image exists or the deadline passes — an admin can never blind-decide early.
- **Stale capture prevention:** When a spot goes free, the backend wipes all `review_*` fields on the spot **and deletes the `spot_captures/{spot_id}` document**, so the next car can never inherit the previous car's photo.
- **Duplicate OCR reads:** `LPR_DEDUP_CACHE` (TTL 120 s) records recently-seen plates. *(Currently written to but never read — dedup is effectively handled by the active-log checks.)*
- **Offline sensor:** The dashboard marks a spot OFFLINE when `last_seen` is older than 2 minutes and warns admins by toast.

### 3.4 SSE Broadcasting

Two independent in-memory client lists:
- `sse_clients` (dashboard): each client stores `role`/`is_special_needs`; `broadcast_event()` sends everything to admins, but only category-matching `spot_update`s to other roles. Log events go to admins only.
- `display_sse_clients` (hardware): keyed by normalized `display_id`. `queue_display_command()` writes the command to the in-memory `display_command_store` (poll fallback, one slot per display — newest wins) *and* pushes it over SSE.

Display command hold times (backend-controlled): Scanning 3 s, Welcome 5 s, Manual review 8 s, Reject 25 s, Spot cleared 1.5 s.

### 3.5 Auth

`get_current_user` verifies the Firebase ID token (with 10 s clock-skew tolerance), then looks up the user document by email in Firestore. `get_current_admin` additionally requires `role == "admin"`. Hardware endpoints are **unauthenticated** (identified by MAC address only). CORS is currently `allow_origins=["*"]` (to be locked down to the Firebase Hosting origin in production).

---

## 4. Firestore Database Schema

| Collection | Doc ID | Fields | Purpose |
|---|---|---|---|
| `parking_spots` | spot id (e.g. `A1`) | `sensor_mac`, `camera_mac`, `category`, `is_occupied`, `battery_level`, `last_seen`, optional `display_id`, and transient `review_capture_path/at`, `review_started_at`, `review_resolve_after`, `review_status` | Live state + hardware mapping per spot |
| `users` | email | `name`, `email`, `role` (`admin`/`student`/`lecturer`/`staff`/`special-needs-driver`), `created_at` | Accounts & authorization roles |
| `vehicles` | license plate (digits) | `license_plate`, `user_id` (email), `created_at` | Plate → owner mapping |
| `parking_logs` | auto-ID | `spot_id`, `license_plate` (real or sentinel), `user_id`, `snapshot_role`, `entry_time`, `exit_time` (null = active), `is_violation`, optional `capture_base64` | Historical sessions + violation evidence |
| `spot_captures` | sanitized spot id | `image_base64`, `updated_at` | Temporary photo held only during manual review; deleted when the spot frees |

MAC lookups check the new field name first (`sensor_mac`/`camera_mac`) then fall back to the legacy `mac_address` field, trying exact/upper/lower-case variants. Active-log queries avoid composite indexes by filtering on `spot_id` + `exit_time == None` and picking the newest `entry_time` in Python.

Category/role model: a spot `category` must equal the driver's `role` (admins park anywhere). The `special-needs-driver` role sees and matches `special-needs-driver` spots.

---

## 5. Manual Review ("Ghost Log") Flow

1. **Trigger:** OCR finds no valid 7–8 digit plate in the image, or a heartbeat marks a spot occupied before any photo arrives. A log with `license_plate = "UNIDENTIFIED"`, `is_violation = true` is created; the LCD shows "Admin review / Check dashboard" (or "Scanning / Please wait" for the heartbeat-first case).
2. **Photo storage:** The camera image is base64-encoded into `spot_captures/{spot_id}`; the spot document gets `review_capture_path` (+ cache-busting `review_capture_at`) and `review_status = "photo_review"`.
3. **Dashboard:** The admin's spot card renders the live image inline with **Accept Vehicle** / **Reject Vehicle** buttons. Buttons are disabled while no image exists — unless the 30 s deadline passes (`missing_photo`), which unlocks a blind decision.
4. **Accept:** log → `MANUAL_ACCEPTED` (authorized, admin recorded as `user_id`), review fields cleared, LCD shows "Welcome / Admin approved".
5. **Reject:** log → `REJECTED` with the image copied permanently into `capture_base64`; LCD shows "Access denied / Please remove car" (25 s hold, re-queued on every subsequent heartbeat while the car stays). The security log gains a realtime "Show Picture" evidence button.
6. **Cleanup:** When the car finally leaves, the heartbeat closes the log, clears review fields, deletes the temp capture, and (for rejected spots) shows "Spot clear / Thank you".

---

## 6. ESP32 Firmware

### 6.1 Shared Protocol (`ParkMeCommon/ParkMeCommon.h`)

Header-only helpers shared by both sketches: state enums, battery-percent math, distance classification, JSON field extractors (no ArduinoJson dependency), MAC parse/format, HTTP status parsing, and the ESP-NOW message structs:

- `EspNowSensorStateMessage` (sensor → camera): magic `0x504D4553` ("PMES"), version, sequence, state, battery, `spotId`, sender MAC.
- `EspNowCameraAckMessage` (camera → sensor): sequence, status (`RECEIVED`, `CAPTURE_STARTED`, `CAPTURE_COMPLETED`, `CAPTURE_FAILED`, `SPOT_FREED`), detail string.

Envelope validation (magic + version + type) rejects foreign ESP-NOW traffic.

### 6.2 Sensor Node (`ParkMeSensorNode.ino`) — dual-core FreeRTOS

**Core 1 (Arduino `loop()`), never blocks on network:**
- Calibration button (dedicated push-button on GPIO 13 → GND, internal pull-up; hold 4 s while running): the technician places a target at the parked-car bumper position, the node averages 15 samples, adds `PARKME_SENSOR_CALIBRATION_MARGIN_CM` (10 cm), and stores the result in NVS as this node's occupied threshold, with PASS/FAIL feedback on the OLED (FAIL if no echo or the nearest object is beyond 150 cm). Uncalibrated nodes fall back to the compiled default (20 cm). Per-node, survives reboot, no re-flash to recalibrate.
- Ultrasonic sampling every 500 ms (3 samples averaged); classification: ≤ calibrated threshold ⇒ OCCUPIED, ≤ free-distance limit ⇒ FREE, else UNKNOWN (ignored).
- ESP-NOW state send on every change (sequence increments) plus a 2 s periodic re-sync; direct peer + broadcast.
- OLED rendering via a low-level SSD1306 driver with a built-in 5×7 font (uppercase A–Z, 0–9 only). It is the *only* code that touches I2C.
- Consumes camera ACKs (from the ESP-NOW receive ISR via a spinlock-protected mailbox) → local messages "Camera ready/Queued", "Taking photo/Please hold", "Photo sent/Checking plate", "Photo failed/Check dashboard".
- Consumes server display commands from the shared struct.

**Core 0 (`networkTask`):**
- Maintains WiFi; connects to `GET /api/v1/displays/stream` (SSE) with exponential backoff 3 s → 30 s; while disconnected, falls back to polling `/displays/poll` every 750 ms.
- Parses SSE `display_command` events and hands them to Core 1 through the mutex-protected `sharedDisplay` struct.
- Sends heartbeats flagged by Core 1 (`sharedSensor.needsTelemetry`) and display ACKs (`/displays/result`) — including *while* the SSE read loop is active (checked every 100 ms inside the loop).
- Persists an unsent heartbeat to NVS (`pendingTelemetry`, single slot) and flushes it when connectivity returns.

**Display priority model:** server SSE messages are definitive — they override any local camera message and hold for their `hold_ms`; local ESP-NOW messages are ignored while a server message is active; when nothing is held, the idle screen shows `Spot <ID> / Occupied|Free <cm> B<battery>%`.

**Telemetry cadence:** send on state change, plus a 20 s heartbeat (`PARKME_SENSOR_HEARTBEAT_INTERVAL_MS`); free-state heartbeats enabled via `PARKME_SENSOR_ALLOW_FREE_HEARTBEATS`.

### 6.3 Camera Node (`ParkMeCameraNode.ino`) — single core

- AI-Thinker pin map; JPEG at VGA/quality 10 with PSRAM (`fb_count = 2`), else QVGA/quality 12.
- ESP-NOW receive ISR stores the sensor message in a spinlock-protected mailbox; `loop()` (50 ms cadence) drains it.
- **One capture per occupancy cycle:** an OCCUPIED trigger queues exactly one capture (`currentCycleCaptureAttempted` latches); nothing more happens until a FREE message resets the cycle. Spot ID in the trigger is deliberately not validated.
- **Capture procedure ("old photo" fix):** flash LED on (80 ms exposure settle) → **two dummy `esp_camera_fb_get()` grabs** to flush the FIFO (needed because `fb_count = 2`) → real grab → flash off.
- **Upload ("1 photo, 3 sends" design):** the single captured frame is POSTed as multipart to `/api/v1/sensors/park`; on connect failure or response timeout it waits 1 s and re-sends the *same frame*, up to 3 attempts total. The frame buffer is released only after the retry loop.
- ACKs at each stage keep the sensor's OLED informed; the backend's response (`WELCOME`/`DENIED`) optionally pulses a gate relay (`PARKME_GATE_RELAY_PIN`, disabled at `-1` by default).

> **Pending merge:** branch `origin/Amir_after_camera_buffer_fix` (one commit ahead) makes the retry loop abort instantly if the sensor broadcasts FREE mid-retry (`checkIfSpotBecameFree()`), so the camera never wastes up to ~24 s uploading a photo of a car that already left.

### 6.4 Known Firmware/Doc Gaps (relevant when testing)

- The `POST /api/v1/telemetry/bulk` endpoint exists and works, but the current sensor firmware never calls it; offline resilience is limited to the single latest state stored in NVS. Multi-event offline history is **not** replayed.
- `ParkMeSensorNode.ino` still contains a legacy synchronous path (`publishCurrentState()`, `handleDisplayPolling()`) that is no longer called from `loop()` — dead code kept from the pre-dual-core design.
- `PARKME_GATE_MAX_CAPTURE_RETRIES` in `SECRETS.example.h` is unused; the retry count is hardcoded to 3 in `captureAndUpload()`.
- `LPR_DEDUP_CACHE` in the backend is written but never read.

### 6.5 Configuration (`ESP32/SECRETS.h`)

Copy `SECRETS.example.h` → `SECRETS.h` (git-ignored). Key values: WiFi credentials; `PARKME_SERVER_SCHEME/HOST/PORT`; `PARKME_GATE_SPOT_ID` (must equal a Firestore `parking_spots` doc ID); `PARKME_DISPLAY_ID` (e.g. `display-c1` — the backend derives `display-<spot_id_lowercase>` unless the spot doc has an explicit `display_id`); `PARKME_CAMERA_ESPNOW_PEER_MAC` (the camera's STA MAC, printed on its serial at boot); pins, thresholds, timeouts. TLS uses `setInsecure()` (no certificate validation) on both nodes.

Flashing instructions: see `ESP32/hardware-upload-guide.md` (board types, FTDI wiring for the CAM, IO0-to-GND flash mode, 115200 serial).

---

## 7. Frontend (`Frontend/app.js`, ~815 lines)

- **API base autodetect:** `window.PARKME_API_BASE` override → Firebase-hosted origins use the configured Cloud Run URL → otherwise same-origin (`/api/v1`, the local FastAPI case).
- **Auth:** Firebase compat SDK `signInWithEmailAndPassword`; the ID token is stored in `localStorage` and sent as a Bearer header; auto-login if the stored JWT hasn't expired.
- **Live updates:** `EventSource` on `/api/v1/stream?token=…` handling `spot_update` (re-render card), `log_event` (prepend security log + refresh stats), `log_aborted` (rewrite log text, drop evidence button). Auto-reconnect after 3 s on error.
- **Defensive polling on top of SSE:** full spot refetch every 5 s (diffed — only changed cards re-render), offline/health scan every 2 s, admin stats refresh every 60 s.
- **Spot cards** (`createSpotCard`): status classes free / occupied / violation / unidentified / offline. Admins additionally see battery, last ping, offline warnings, the review image + Accept/Reject buttons (with pending/disabled states via `pendingReviewSpotIds`), and rejected-spot evidence. Non-admins see only their category with plates hidden, plus a recommendation banner suggesting the first verified-free spot.
- **Offline rule:** `last_seen` older than 2 minutes (`SPOT_STALE_MS`) ⇒ card shows OFFLINE; admin gets a toast on the transition, and offline spots are excluded from recommendations.
- **Security log:** violation entries get a "Show Picture" button that fetches `/logs/{id}/capture` as a blob and swaps in the image.

`index.html` loads Firebase compat SDKs, tries Firebase Hosting auto-config (`/__/firebase/init.js`), and `app.js` falls back to the hardcoded ParkMe Firebase web config for local runs.

---

## 8. Key Timings & Thresholds (single reference table)

| Constant | Value | Where | Meaning |
|---|---|---|---|
| Occupied threshold | calibrated per node (default 20 cm) | firmware | Distance ≤ this ⇒ OCCUPIED; set by button calibration = measured car distance + 10 cm margin |
| Sensor sample interval | 500 ms (3×120 ms pulses) | firmware | Ultrasonic cadence |
| Heartbeat interval | 20 s | firmware | Occupied-state confirmation to backend |
| ESP-NOW re-sync | 2 s | firmware | Periodic state re-broadcast |
| Camera upload attempts | 3 (same frame) | firmware | 1 photo, up to 3 sends, 1 s between |
| Camera HTTP timeout | 7 s | firmware | Per upload attempt |
| Bouncy-driver window | 90 s | backend | Exit within window ⇒ log ABORTED |
| Camera-first grace | 10 s | backend | Heartbeat won't clobber a fresh camera log |
| Review photo deadline | 30 s | backend | After this, admin may blind Accept/Reject |
| LPR dedup TTL | 120 s | backend | (currently unused read-side) |
| Display SSE keepalive | 15 s | backend | Comment pings to keep firewalls happy |
| SSE reconnect backoff | 3 s → 30 s | firmware | Exponential |
| Display poll fallback | 750 ms | firmware | When SSE is down |
| Frontend spot stale | 2 min | frontend | OFFLINE badge threshold |
| Frontend full refresh / health scan / stats | 5 s / 2 s / 60 s | frontend | Polling safety nets |
| LCD holds: scanning / welcome / review / reject / cleared | 3 / 5 / 8 / 25 / 1.5 s | backend | Sent as `hold_ms` |

---

## 9. Running, Seeding & Deployment

### Local development

```powershell
# Option A: one-click (creates .venv, installs deps, runs on 0.0.0.0:8000)
Backend\run_local_backend.ps1

# Option B: manual
cd Backend
.venv\Scripts\activate     # or source venv/bin/activate on macOS/Linux
uvicorn main:app --reload
```

- Dashboard: http://127.0.0.1:8000/ (FastAPI serves `Frontend/` statically) — API docs at `/docs`.
- Requires `Backend/.env` (or `env`) with `GOOGLE_APPLICATION_CREDENTIALS=./serviceAccountKey.json` and `FIREBASE_PROJECT_ID`. The service account key is git-ignored; get it from Firebase Console → Project Settings → Service Accounts.
- **There is no emulator layer** — local runs talk to the real Firestore and Vision APIs.

### Seeding test data

```bash
cd Backend
python seed_firestore.py      # wipes & seeds parking_spots (A1..C2), users, vehicles
python create_auth_users.py   # creates matching Firebase Auth accounts (password123)
```

Seeded identities: `admin@` (admin), `student@` (plate 1234567), `lecturer@` (9876543), `jane@` (special-needs, 1122334) — all `@technion.ac.il`.

### Deployment

- **Backend → Cloud Run:** `gcloud run deploy parkme-backend --source Backend --region me-west1 --allow-unauthenticated`, or the `cloudbuild.yaml` pipeline (build → GCR push → deploy with `ENVIRONMENT=production`). Cloud Run injects `$PORT`; ADC replaces the key file.
- **Frontend → Firebase Hosting:** `firebase deploy --only hosting` (public dir `Frontend`). After deploying, point `app.js`'s Cloud Run URL placeholder at the real backend and tighten backend CORS to the hosting origin.
- **ESP32:** set `PARKME_SERVER_HOST` to the Cloud Run host, scheme `https`, port 443, and reflash.

---

## 10. Testing Assets

| Location | What it is | Status |
|---|---|---|
| `tests/test_backend_parking_logic.py` | Unit tests for `should_preserve_recent_active_log` / `seconds_since` (timezone handling, preserve/reject cases) | ✅ Working; run with `python -m unittest tests.test_backend_parking_logic` from repo root |
| `tests/test_backend_database.py` | Legacy SQLite schema tests | ❌ **Broken/stale** — imports a missing `_support` module and tests the removed SQLite database |
| `Unit Tests/HW_Ultrasonic_Distance_Test` | HC-SR04 validation sketch (PASS/FAIL on serial) | Hardware-in-the-loop |
| `Unit Tests/HW_ESP32CAM_Capture_Test` | Camera init + WiFi + JPEG grab validation | Hardware-in-the-loop |
| `Unit Tests/HW_OLED_SSD1306_I2C_Test` | OLED address + WELCOME/PARKME render | Hardware-in-the-loop |
| `ESP32/ParkMeFirmwareCompileTests` | Compile-time (static_assert) tests of shared decision logic | Compile in Arduino IDE |
| `ESP32/ScreenProbe` | I2C bus scanner for display debugging | Diagnostic tool |

Backend integration coverage of `main.py` (heartbeat/park/review state machine) is currently **zero** — the highest-value gap for the testing phase.

---

## 11. Security Notes

- Never commit `serviceAccountKey.json`, `.env`/`env` with real values, or `ESP32/SECRETS.h` (only `SECRETS.example.h` belongs in git).
- Hardware endpoints trust MAC addresses without authentication; ESP32 TLS skips certificate validation (`setInsecure()`); CORS is wide open — all acceptable for the course prototype, all noted for production hardening.
- The Firebase web config in `app.js` is public by design (client-side identifiers, not secrets).
