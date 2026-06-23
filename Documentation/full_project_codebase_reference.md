# ParkMe Full Project Codebase Reference

Code-first snapshot of the repository as scanned on 2026-06-23.

This file is intended to be the most comprehensive single-document reference in the repo. It was written by reading the current backend, frontend, ESP32 firmware, tests, top-level files, active documentation, legacy documentation, and generated/supporting directories.

Important rule for future readers:

- When this file disagrees with an older document in `docs/` or `Documentation/`, the current source code in `Backend/main.py`, `Frontend/app.js`, `ESP32/`, and the local configuration files should be treated as the source of truth.

## 1. Project Purpose

ParkMe is a smart parking system for campus-style parking management.

Its main goals are:

- detect whether a parking spot is physically free or occupied
- identify vehicles through a camera and OCR
- decide whether the vehicle is allowed to park in that category of spot
- surface violations and anomalies to an admin dashboard in real time
- keep a history of parking sessions and anomaly events
- show status messages on a spot-side display driven by the backend

The current implementation is no longer the original SQL + local OCR version. The active codebase is centered on:

- ESP32 sensor nodes
- ESP32-CAM camera nodes
- a FastAPI backend
- Firebase Firestore
- Firebase Authentication
- Google Cloud Vision OCR
- a vanilla HTML/CSS/JS web frontend with Server-Sent Events

## 2. Current Runtime Architecture

At runtime, the system is split into four main layers:

1. Edge sensor/display node:
   - runs `ESP32/ParkMeSensorNode/ParkMeSensorNode.ino`
   - reads the HC-SR04 ultrasonic sensor
   - reads battery level
   - persists calibration and one pending telemetry item in NVS
   - polls the backend for display commands
   - renders both local status and backend messages on an OLED

2. Edge camera node:
   - runs `ESP32/ParkMeCameraNode/ParkMeCameraNode.ino`
   - does not decide on its own when to capture
   - polls the backend for capture commands
   - captures a JPEG only when the backend asks it to
   - uploads the image to the backend
   - reports command completion or failure back to the backend
   - in the current local `ESP32/SECRETS.h`, the gate relay is disabled with `PARKME_GATE_RELAY_PIN = -1`, so hardware gate actuation is currently off unless reconfigured

3. Backend:
   - runs `Backend/main.py`
   - maps device MACs to logical spot IDs using Firestore
   - manages occupancy state
   - runs OCR through Google Cloud Vision
   - decides authorization and violations
   - stores live state, logs, review-image metadata, and command queues in Firestore
   - pushes live events to the frontend through SSE
   - serves the frontend statically

4. Web frontend:
   - runs from `Frontend/index.html`, `Frontend/app.js`, `Frontend/style.css`
   - authenticates through Firebase Auth
   - asks the backend for profile, spots, logs, and stats
   - keeps an open SSE stream
   - lets admins accept, reject, or resolve anomalies

## 3. End-to-End Workflows

### 3.1 Sensor Node Lifecycle

The sensor node:

- boots
- initializes the OLED graphics display if enabled
- loads stored baseline calibration from NVS
- loads one pending telemetry record from NVS
- connects to Wi-Fi
- samples distance every second
- classifies the reading as `FREE`, `OCCUPIED`, or `UNKNOWN`

Only known states are published. Invalid or out-of-range sensor readings are ignored locally and are not sent to the backend.

Telemetry is sent when:

- this is the first known state after boot
- the state changes between `FREE` and `OCCUPIED`
- the heartbeat timer expires and free-heartbeats are enabled

The current local firmware settings in `ESP32/SECRETS.h` make this behavior:

- sample interval: `1000 ms`
- heartbeat interval: `60000 ms`
- free heartbeats: enabled
- Wi-Fi retry interval: `10000 ms`
- HTTP timeout: `5000 ms`

If a publish fails, the node stores one pending telemetry item in NVS and retries it after Wi-Fi returns.

### 3.2 Heartbeat Processing in the Backend

`POST /api/v1/sensors/heartbeat` is the backend’s main occupancy endpoint.

The backend:

- receives `mac_address`, `is_occupied`, and `battery_level`
- resolves the spot by matching `sensor_mac` or legacy `mac_address`
- finds the latest active parking log for that spot
- decides whether this is a new arrival, a steady occupied state, or a departure

On an arrival:

- if an old active log still exists, it is force-closed as stale
- if there is no active log, a new active log is created with `license_plate = "UNIDENTIFIED"`
- a camera capture command is queued for the mapped camera
- a display command saying `Scanning / Please wait` is queued for the spot-side display

On a steady occupied state:

- the backend does not queue duplicate camera commands
- this prevents repeated image requests while the same car is still present

On a departure:

- the active log is closed with `exit_time`
- if the duration was shorter than `BOUNCY_DRIVER_MAX_SECONDS = 90`, and the session was not already admin-reviewed, the log is rewritten to `license_plate = "ABORTED"` and `is_violation = False`
- pending camera commands for that spot are cancelled
- review-image metadata is cleared from the spot document

### 3.3 Camera Command Workflow

The camera node is backend-driven.

Flow:

1. Backend queues a document in `camera_commands`.
2. Camera polls `POST /api/v1/cameras/poll`.
3. Backend claims the pending command and returns `action = CAPTURE`.
4. Camera captures and uploads a JPEG to `POST /api/v1/sensors/park`.
5. Camera interprets the backend response as `WELCOME`, `DENIED`, or `RETRY`.
6. Camera retries locally up to `PARKME_GATE_MAX_CAPTURE_RETRIES = 3`.
7. Camera reports final command status to `POST /api/v1/cameras/result`.

Important detail:

- the camera no longer acts as a physical gate sensor in the active architecture
- it is a polled worker that executes backend-issued capture jobs

### 3.4 Camera Upload and OCR Workflow

`POST /api/v1/sensors/park` handles image uploads.

The backend:

- maps `camera_mac` to the spot
- reads the uploaded JPEG
- calls Google Cloud Vision twice:
  - `text_detection`
  - `document_text_detection`
- extracts only numeric characters from the OCR text

If OCR fails:

- the image is saved to `Backend/captures/` using a UUID-based filename
- `review_capture_path` and `review_capture_at` are written to the spot document
- a display command `Scan again / Hold still` is queued
- the camera receives `action = RETRY`

If OCR succeeds:

- the backend checks for duplicate reads of the same plate within 5 seconds
- if duplicated, the backend drops it and returns `RETRY`
- otherwise, the backend looks up the vehicle in Firestore
- if the vehicle exists, it fetches the user and role
- it compares the role to the spot category
- it updates the active log or creates a new one
- it clears review-image metadata from the spot
- it broadcasts the final occupied state over SSE
- it queues a display command of either:
  - `Welcome / <driver-name-or-message>`
  - `Access denied / access denied`

### 3.5 Display Command Workflow

The sensor/display node polls:

- `POST /api/v1/displays/poll`
- `POST /api/v1/displays/result`

The backend stores display commands in `display_commands` with:

- `request_id`
- `action`
- `status`
- `display_id`
- `spot_id`
- `title`
- `message`
- `hold_ms`
- timestamps and optional detail fields

The sensor node:

- polls every `1000 ms`
- renders the backend-provided title/message
- keeps that message active until `hold_ms` expires
- then falls back to its local screen view showing the spot state and battery level

### 3.6 Frontend Workflow

The frontend:

- loads Firebase compat SDKs in `Frontend/index.html`
- signs users in with `firebase.auth().signInWithEmailAndPassword`
- stores the Firebase ID token in `localStorage`
- calls `GET /api/v1/users/me` to get the user profile and role
- calls `GET /api/v1/spots`
- if admin, also calls:
  - `GET /api/v1/logs`
  - `GET /api/v1/admin/usage-stats`
- opens `GET /api/v1/stream?token=...` as an SSE connection

The frontend keeps a `currentSpots` map and updates the DOM card-by-card whenever a `spot_update` arrives.

### 3.7 Admin Review Workflow

The current anomaly-review behavior is more advanced than the older docs.

After repeated OCR failure:

- the spot remains logically `UNIDENTIFIED`
- the backend eventually exposes `review_status = "ready"`
- the frontend shows the last stored review image
- the frontend shows three admin actions:
  - `Accept Vehicle`
  - `Reject Vehicle`
  - `Resolve Spot`

Their current meanings are:

- `Resolve`
  - active unidentified log is rewritten to `RESOLVED`
  - frontend shows the spot as empty
  - review image is cleared
  - any pending capture command is cancelled

- `Accept`
  - active unidentified log is rewritten to `MANUAL_ACCEPTED`
  - frontend shows the spot as occupied
  - the plate label becomes `OCCUPIED (ADMIN ACCEPTED)`
  - review image is cleared
  - pending capture command is cancelled

- `Reject`
  - active unidentified log is rewritten to `REJECTED`
  - frontend keeps showing the spot as occupied/violation
  - review image is cleared
  - pending capture command is cancelled
  - the spot only becomes free when the car physically leaves

This means the frontend is intentionally not a direct mirror of the physical `parking_spots.is_occupied` field. It renders an effective state built from both the physical spot document and the latest active log.

## 4. Actual Data Model in the Current Code

The active runtime data model is larger than the original four Firestore collections.

### 4.1 `users`

Used for role and profile lookup.

Current behavior:

- backend looks users up by `email`
- `get_current_user()` queries Firestore by the `email` field
- the seeder uses the email as the document ID

Typical fields:

- `name`
- `email`
- `role`
- `points`
- `created_at`

### 4.2 `vehicles`

Maps a license plate to the owning user.

Current behavior:

- vehicle document ID is the license plate string
- `user_id` points at a user document

Typical fields:

- `user_id`
- `created_at`

### 4.3 `parking_spots`

Represents the live physical state of a spot and its hardware routing.

Important fields seen in code and docs:

- `category`
- `sensor_mac`
- `camera_mac`
- legacy `mac_address`
- `display_id`
- `is_occupied`
- `battery_level`
- `last_seen`
- `review_capture_path`
- `review_capture_at`

Key point:

- `parking_spots` is the live physical state
- it is not the sole truth for the visible UI state
- the frontend-visible logical state is computed by combining `parking_spots` and `parking_logs`

### 4.4 `parking_logs`

Append-style historical ledger for parking sessions and anomalies.

Fields used in current code:

- `spot_id`
- `license_plate`
- `user_id`
- `snapshot_role`
- `entry_time`
- `exit_time`
- `is_violation`

Special `license_plate` values currently used by the backend:

- `UNIDENTIFIED`
- `ABORTED`
- `RESOLVED`
- `REJECTED`
- `MANUAL_ACCEPTED`

### 4.5 `camera_commands`

This collection is a backend-to-camera queue, not user-facing business data.

Document ID:

- normalized `camera_mac`

Fields:

- `request_id`
- `action`
- `status`
- `camera_mac`
- `spot_id`
- `reason`
- `queued_at`
- `claimed_at`
- `completed_at`
- `detail`

Behavior:

- only one current command document exists per camera MAC
- older commands are overwritten or cancelled rather than accumulated

### 4.6 `display_commands`

This collection is a backend-to-display queue.

Document ID:

- normalized `display_id`

Fields:

- `request_id`
- `action`
- `status`
- `display_id`
- `spot_id`
- `title`
- `message`
- `hold_ms`
- `queued_at`
- `claimed_at`
- `completed_at`
- `detail`

### 4.7 Review Image Storage

Review images are not stored in Firestore blobs and are not uploaded to Firebase Storage.

Current implementation:

- JPEG bytes are saved on disk under `Backend/captures/`
- Firestore only stores the relative path and capture timestamp
- the backend serves `/captures/...` as static files

Current folder contents show both:

- newer UUID-based review images used by the latest review flow
- older legacy files such as `c1_latest.jpg` and `c1_review.jpg`

This is important because:

- images are tied to the backend filesystem
- they are not durable cloud object storage
- scaling to multiple backend instances would need a shared store later

## 5. Current Timing and State Constants

The current checked code and local config imply these important timings:

| Area | Current value |
|---|---:|
| Sensor sample interval | `1000 ms` |
| Sensor heartbeat interval | `60000 ms` |
| Sensor Wi-Fi retry interval | `10000 ms` |
| Sensor HTTP timeout | `5000 ms` |
| Camera command poll interval | `2000 ms` |
| Camera Wi-Fi retry interval | `10000 ms` |
| Camera HTTP timeout | `10000 ms` |
| Camera max capture retries | `3` |
| Camera retry status delay | `2500 ms` |
| Camera retry backoff | `2500 ms` |
| Backend command stale threshold | `90 s` |
| Bouncy-driver threshold | `90 s` |
| LPR dedup cache TTL | `120 s` |
| Duplicate plate rejection window | `5 s` |
| Frontend spot stale threshold | `120000 ms` |
| Display poll interval | `1000 ms` |

## 6. Edge Cases That Are Explicitly Handled

This section describes the actual current code behavior, not the older or aspirational docs.

### 6.1 Unknown Sensor Readings

Handled in sensor firmware.

If the ultrasonic reading is:

- `<= 0`
- or above the free-distance limit

then it becomes `STATE_UNKNOWN`.

Current behavior:

- the sensor logs the invalid reading to serial
- it does not publish an unknown state to the backend

This prevents the backend from thrashing between free/occupied due to bad echoes.

### 6.2 Sensor Wi-Fi Loss

Handled in sensor firmware.

If telemetry cannot be posted:

- one pending telemetry item is stored in NVS
- the node retries after Wi-Fi recovers

Limitation:

- it stores only the latest pending state, not a full event history

### 6.3 Bulk Replay Support Exists, but the Main Sensor Firmware Does Not Use It

Handled partly in backend and partly not used by the current sensor firmware.

`POST /api/v1/telemetry/bulk` can replay cached chronological events.

But the active sensor code currently uses:

- single-state NVS caching
- then re-sends that latest state through the normal heartbeat path

So the bulk endpoint is present and useful, but not the main path used by current sensor firmware.

### 6.4 Stale Active Log Before a Fresh Arrival

Handled in backend heartbeat logic.

If the spot was previously free but a supposedly active log still exists:

- the backend closes the stale log first
- then starts a fresh arrival cycle

This avoids carrying corrupted old sessions into a new car event.

### 6.5 Ghost Log Creation

Handled in backend heartbeat logic.

If a spot becomes physically occupied and no active log exists:

- a new active log is created with `UNIDENTIFIED`
- this guarantees that physical occupancy is represented immediately even if OCR has not completed yet

### 6.6 Ghost Log Self-Healing

Handled in camera upload logic.

If the camera result arrives after a ghost log was created:

- the backend overwrites the active `UNIDENTIFIED` log
- it fills in the real license plate, user, role snapshot, and violation status
- it preserves the original `entry_time`

### 6.7 Repeated Capture Failures

Handled across backend, camera firmware, and frontend.

If OCR keeps failing:

- the backend stores the last failed image for admin review
- the camera node retries locally up to 3 times
- if all retries fail, the backend marks the review state as ready
- the frontend shows the last image and admin controls

### 6.8 Latest Review Image Caching Problem

Handled in the current code by:

- writing each review image to a unique UUID-based filename
- appending `?v=<timestamp>` to the served image path

This reduces browser reuse of an older image and helps the frontend show the latest failed capture.

### 6.9 Duplicate Camera Command Suppression

Handled in backend command queue logic.

If a command already exists for a camera and is still fresh:

- the backend reuses it instead of creating duplicates

On a genuine new arrival:

- the command can be replaced intentionally

### 6.10 Duplicate License Plate Reads

Handled in backend OCR flow.

If the same plate is seen again within 5 seconds:

- the backend does not create another session
- it returns `RETRY` with reason `duplicate_within_5s`

### 6.11 Bouncy Driver

Handled on departure in backend heartbeat and bulk paths.

If a car leaves within 90 seconds and the session was not already converted to:

- `RESOLVED`
- `REJECTED`
- `MANUAL_ACCEPTED`

then the backend:

- sets `exit_time`
- forces `license_plate = "ABORTED"`
- clears the violation flag

This prevents short hesitation events from remaining as real violations.

### 6.12 Admin Review States Persist Until Physical Departure or Explicit Change

Handled by `build_effective_spot_state()`.

Meaning:

- `RESOLVED` displays as empty
- `MANUAL_ACCEPTED` displays as occupied and non-violating
- `REJECTED` displays as occupied and violating

This effective-state layer is what keeps admin decisions visible on the frontend even though the underlying physical sensor may still be reporting occupied.

### 6.13 Reject Stops More Pictures for the Same Car

Handled indirectly by:

- cancelling pending capture commands when reject is pressed
- not queuing a new capture while the spot remains steadily occupied and still has an active log

Pictures start again only when:

- the spot becomes free
- then later a new physical arrival happens

### 6.14 Spot Becomes Free After Admin Reject

Handled correctly in current logic.

If a rejected car leaves:

- the active log is closed
- the spot becomes free again
- the next arrival starts a new cycle from scratch

### 6.15 Offline Spot Detection in the Frontend

Handled only in the frontend.

If `last_seen` is older than 2 minutes:

- the spot card becomes `OFFLINE`
- admins get a toast when it first becomes stale
- another toast appears if the spot later comes back online

This is a UI-level interpretation; the backend does not currently emit dedicated offline-alert events.

### 6.16 Display Address Fallback

Handled in the sensor/display node.

If the configured OLED I2C address does not answer:

- the node scans the I2C bus
- uses the first detected address instead

This is helpful when the module is SH1106-like or wired with a different default address.

### 6.17 Display Message Truncation and Normalization

Handled in the sensor/display node.

The display code:

- strips unsupported characters
- uppercases text
- truncates long text to fit
- splits the body into two lines

This prevents ugly rendering and reduces display corruption risk.

### 6.18 Expired Saved Web Token

Handled in the frontend.

The frontend checks the JWT `exp` value before auto-login. If expired:

- it removes the token instead of trying to start the dashboard blindly

This is better than the older behavior described in `bug_report.md`.

## 7. Important Edge Cases That Still Need Human Attention or More Engineering

These are real project limitations visible from the current repo.

### 7.1 HMAC Security Is Documented but Not Implemented in the Active Backend

Many docs mention hardware HMAC verification.

Current code reality:

- `Backend/main.py` does not implement request-signature verification middleware
- `ESP32/SECRETS.h` contains `PARKME_HARDWARE_HMAC_SECRET`, but it is empty in the local file
- hardware auth is effectively based on device MAC mapping and network reachability, not cryptographic signing

This is one of the biggest documentation-to-code mismatches in the repo.

### 7.2 Some Docs Still Describe Removed or Replaced Architecture

Examples of outdated statements in older docs include:

- `POST /api/v1/auth/login` still exists
- OpenCV + Tesseract are still the OCR path
- camera uploads include `spot_id`
- HMAC is enforced
- the camera node self-detects cars at the gate and drives the whole flow
- 45-second cooldown and 60-second bounce timing are still current

The code no longer matches those descriptions.

### 7.3 Review Images Are Filesystem-Local

The review-image feature currently depends on `Backend/captures/`.

Implications:

- images are not in the database
- images are not on Firebase Storage or Cloud Storage
- multiple backend instances would not automatically share them
- deleting the backend filesystem would lose them

### 7.4 Firestore Composite Indexes Must Be Created Manually

The repo repeatedly documents this, and it is still true.

The code assumes Firestore queries succeed, but the necessary indexes may need manual creation the first time certain queries are used.

### 7.5 External Dependency on Google Cloud Vision

If Vision API is disabled, not billed, or credentials are wrong:

- OCR fails
- camera flow degrades into repeated retries and review-state handling

### 7.6 No Out-of-Band Alerting

The frontend can mark a spot offline and admins can see anomalies while the dashboard is open.

What is still missing:

- email alerts
- SMS alerts
- push notifications
- background watcher/monitor service

### 7.7 Empty or Unfinished Areas in the Repo

These are present but not active product features:

- `ESP32/ParkMeDisplayNode/` is empty
- `Unit Tests/HW_LCD_I2C_Test/` is empty
- `flutter_app/` only contains a placeholder file
- `Backend/templates/` is empty
- `Documentation/connection diagram/` contains placeholders, not an actual diagram asset set

### 7.8 Absolute Include Paths in Firmware Config Headers

`ESP32/ParkMeSensorNode/ParkMeConfig.h` and `ESP32/ParkMeCameraNode/ParkMeConfig.h` include:

- `C:/Users/georg/OneDrive/Desktop/IOT_ParkMe/ESP32/SECRETS.h`

That means:

- the local firmware setup is machine-specific
- compilation portability is weaker than it should be
- another machine may need to edit those headers or use the library wrapper path instead

### 7.9 Python Test Coverage Is Not Aligned with the Current Runtime

The only visible Python test source file is:

- `tests/test_backend_database.py`

It targets the old SQLite schema path and imports `_support`, but `_support.py` is not present as source in `tests/`.

This suggests:

- Python tests are incomplete or stale
- Firestore runtime behavior is mostly not covered by automated tests in this repo

### 7.10 Some Seeder and Schema Files Are Historical, Not Runtime Truth

`Backend/schema.sql` and the Python database test file reflect the older SQL-era architecture.

The live backend does not use SQLite in production or development runtime anymore.

### 7.11 `Backend/env.example` vs `Backend/.env.example`

Both exist.

Current repo implications:

- `.env.example` is the active newer env template
- `env.example` is legacy and still mentions `JWT_SECRET` and a stronger HMAC story than the active code uses

Future maintainers should not assume both are equally current.

## 8. Actual Security Model

### 8.1 Web Authentication

Implemented and active:

- Firebase Auth in the browser
- Firebase ID token verification in the backend
- role lookup from Firestore user profile

### 8.2 Role-Based Visibility

Implemented and active:

- admins see all spots
- non-admin users see only spots relevant to their role
- special-needs users also see `special-needs-driver` spots
- non-admins do not receive license-plate data in spot responses

### 8.3 Admin-Only Endpoints

Implemented and active:

- `GET /api/v1/logs`
- `GET /api/v1/admin/usage-stats`
- `PUT /api/v1/sensors/resolve`
- `PUT /api/v1/sensors/accept`
- `PUT /api/v1/sensors/reject`

### 8.4 Hardware Identity

Implemented and active:

- sensor nodes are matched by `sensor_mac` or legacy `mac_address`
- camera nodes are matched by `camera_mac` or legacy `mac_address`
- display nodes are matched by logical `display_id`

### 8.5 Hardware Request Authentication

Not actively enforced in code:

- there is no current backend HMAC verification middleware
- current docs overstate this capability

## 9. Frontend Rendering Rules

The frontend has a few important rules that matter when debugging system behavior:

- `UNIDENTIFIED` + violation renders as a highlighted anomaly card
- `RESOLVED` renders visually as `EMPTY`
- `MANUAL_ACCEPTED` renders as `OCCUPIED (ADMIN ACCEPTED)`
- `REJECTED` renders as `OCCUPIED (REJECTED)`
- `review_status = retrying` shows a disabled `Camera Retrying...` button
- `review_status = ready` shows the review image and admin action buttons
- `OFFLINE` is computed entirely from `last_seen`, not pushed as a dedicated backend state

The frontend also treats the dashboard as a security-oriented interface:

- log colors differ by anomaly type
- stats are admin-only
- recommendation banner only uses currently visible and non-offline free spots

## 10. Analytics and Stats Behavior

`GET /api/v1/admin/usage-stats` computes statistics by scanning all spot and log documents at request time.

It derives:

- total spots
- occupied spots
- total logs
- authorized sessions
- violation events
- unresolved events
- resolved events
- aborted events
- peak hour
- busiest spot
- average duration

This is simple and readable, but at larger scale it could become expensive because it is not pre-aggregated.

## 11. Repository Map

### 11.1 Root-Level Files and Folders

Main top-level directories:

- `Backend/`
- `Frontend/`
- `ESP32/`
- `Documentation/`
- `docs/`
- `tests/`
- `Unit Tests/`
- `visualizations-hist/`

Other notable root items:

- `README.md` is a short current project entry point
- `guide.md` is an AI-oriented project note and is partly stale
- `common-commands.md` is a simple dev command cheat sheet and is partly stale
- `bug_report.md` is a historical audit, not the current truth
- `Backend.zip` appears to be an archival bundle, not the active source of truth
- `.DS_Store` is irrelevant macOS metadata

### 11.2 Backend Folder

Important runtime files:

- `Backend/main.py`
- `Backend/requirements.txt`
- `Backend/.env.example`
- `Backend/run_local_backend.ps1`
- `Backend/cloudbuild.yaml`
- `Backend/Dockerfile`
- `Backend/seed_firestore.py`
- `Backend/create_auth_users.py`

Historical or non-runtime:

- `Backend/schema.sql` is from the old SQL design
- `Backend/env.example` is legacy
- `Backend/serviceAccountKey.json` is local-only sensitive credential material
- `Backend/env` is local-only

Generated or local-state content:

- `Backend/.venv/`
- `Backend/__pycache__/`
- `Backend/captures/`

### 11.3 Frontend Folder

Files:

- `Frontend/index.html`
- `Frontend/app.js`
- `Frontend/style.css`

This is a fully static frontend with no build system.

### 11.4 ESP32 Folder

Important files and directories:

- `ESP32/SECRETS.example.h`
- `ESP32/SECRETS.h` local/private config
- `ESP32/ParkMeSensorNode/`
- `ESP32/ParkMeCameraNode/`
- `ESP32/ParkMeCommon/`
- `ESP32/ParkMeLcd/`
- `ESP32/ParkMeFirmwareCompileTests/`
- `ESP32/ScreenProbe/`
- `ESP32/libraries/`

Special notes:

- `ESP32/libraries/` contains Arduino-library wrappers around the shared headers
- `ESP32/ParkMeLcd/` is legacy/minimal LCD support
- the local config currently has `PARKME_GATE_LCD_ENABLED = false`, so the old camera-side LCD path is disabled even though the code is still present
- `ESP32/parameters.h` appears to be an orphan from earlier keypad/audio experiments and is not part of the active parking runtime
- `ESP32/ParkMeDisplayNode/` exists but is empty
- `ESP32/compiled_program.bin` is empty
- `ESP32/INO files here.txt` is an empty placeholder

### 11.5 Documentation Folder

`Documentation/` is intended to hold the active docs.

Most useful current files:

- `setup_guide.md`
- `how_to_run_locally.md`
- `system_architecture_and_workflow.md`
- `system_architecture.md`
- `firestore_database_structure.md`
- `api_and_database.md`
- `logging_and_edge_case_behavior.md`
- `hardware_and_edge_cases.md`
- `unhandled_edge_cases_user_guide.md`
- `migration_to_google_cloud_and_firebase.md`
- `user_story_status.md`

This new file belongs in that same group.

### 11.6 `docs/` Folder

`docs/` is a mix of:

- older active-era notes
- historical architecture writeups
- phase-by-phase project evolution docs
- archived duplicates under `docs/archive/`

Useful historical context files:

- `docs/project_summary.md`
- `docs/phase8_architecture.md`
- `docs/sync-issues.md`
- `docs/current_hardware_behavior.md`
- `docs/edge_cases.md`

But they should not override the current source code.

### 11.7 Tests and Hardware Validation

`tests/`

- contains one visible Python source test: `test_backend_database.py`
- this targets the old SQL data model and is not enough to verify the current Firestore backend

`Unit Tests/`

- contains hardware validation sketches
- contains a report template
- includes:
  - ultrasonic test
  - ESP32-CAM capture test
  - OLED display test

Empty:

- `Unit Tests/HW_LCD_I2C_Test/`

### 11.8 Generated and Non-Source Directories

The following are generated, cached, archival, or local-support directories rather than core source:

- `.arduino-build/`
- `arduino-build/`
- `.arduino-data/`
- `.arduino-downloads/`
- `.arduino-user/`
- `visualizations-hist/`
- `.agents/`

These can be useful for local debugging or historical inspection, but they are not the core application logic.

## 12. Local Run and Deployment Story

### 12.1 Local Backend

Preferred local runner in the repo:

- `Backend/run_local_backend.ps1`

What it does:

- creates `.venv` with Python 3.11 if missing
- installs requirements if needed
- runs `uvicorn main:app --host 0.0.0.0 --port 8000 --reload`

### 12.2 Static Frontend Serving

The backend mounts:

- `/captures` from `Backend/captures/`
- `/` from `Frontend/`

That means one local FastAPI server can serve both:

- the API
- the frontend
- the review images

### 12.3 Firebase Hosting

`firebase.json` points Hosting at `Frontend/` with SPA rewrites to `index.html`.

`.firebaserc` still contains:

- `YOUR_FIREBASE_PROJECT_ID`

So it is a template, not a finished deployment configuration.

### 12.4 Cloud Run

`Backend/cloudbuild.yaml` deploys the backend container to:

- Cloud Run service: `parkme-backend`
- region: `me-west1`

### 12.5 Local Credentials and Secrets

Sensitive local-only files currently present or expected:

- `Backend/serviceAccountKey.json`
- `Backend/.env`
- `ESP32/SECRETS.h`

They are intentionally ignored by Git and should remain private.

## 13. Testing Inventory

### 13.1 What Is Tested

Current visible testing assets:

- compile-time assertions in `ESP32/ParkMeFirmwareCompileTests/ParkMeFirmwareCompileTests.ino`
- hardware test sketches in `Unit Tests/`
- one Python database test file for the old SQL model

### 13.2 What Is Not Well Covered

Not obviously covered by automated tests in this repo:

- Firestore query behavior
- Firebase-authenticated API routes
- SSE behavior
- camera command queue behavior
- admin review flows
- review image behavior
- current 90-second bouncing-driver logic
- accept/reject/resolve semantics

## 14. Most Important Current Truths for Future Maintainers

If someone only remembers a few things about this codebase, they should remember these:

1. The backend is now the central coordinator. The camera is a polled worker, not an autonomous gate sensor.
2. `parking_spots` alone does not define what the frontend should show. The visible state comes from active logs plus physical occupancy.
3. Review images are stored on the backend filesystem, not in Firestore blobs or cloud object storage.
4. Admin review now has three paths: accept, reject, and resolve.
5. The bounce window is currently 90 seconds, not 60.
6. Hardware HMAC security is described in several docs but is not actually enforced by the active backend code.
7. A significant amount of repository documentation is historical or partially stale. Current code wins.

## 15. Suggested Reading Order for a New Maintainer

Best practical order:

1. `README.md`
2. this file
3. `Backend/main.py`
4. `Frontend/app.js`
5. `ESP32/ParkMeSensorNode/ParkMeSensorNode.ino`
6. `ESP32/ParkMeCameraNode/ParkMeCameraNode.ino`
7. `Documentation/setup_guide.md`
8. `Documentation/how_to_run_locally.md`
9. `Documentation/firestore_database_structure.md`
10. `Documentation/unhandled_edge_cases_user_guide.md`

## 16. Final Summary

ParkMe is currently a backend-centered, Firestore-backed, Firebase-authenticated IoT parking system with:

- a sensor node that reports physical occupancy and drives a display
- a camera node that performs backend-commanded photo capture
- a backend that resolves OCR, authorization, anomalies, and command queues
- a frontend that reflects live effective state rather than raw physical state

The codebase is functional and fairly robust around real-world messiness such as delayed camera uploads, unreadable plates, stale logs, short stay events, and spot offline detection.

Its biggest remaining weaknesses are not in the core happy path, but in the surrounding engineering maturity:

- documentation drift
- limited automated coverage for current Firestore behavior
- non-enforced hardware authentication
- filesystem-local review image storage
- a few unfinished or placeholder areas left in the repo
