# ParkMe Project Audit Report

Audit date: 2026-07-10 · Branch: `camera_buffer_fix_branch` · Auditor: Claude Code (per `Documentation/CLAUDE_PROJECT_AUDIT.md`)

## 1. Executive Summary

ParkMe is a **working, integrated prototype** whose main end-to-end flow — ultrasonic detection → ESP-NOW camera trigger → photo upload → real Google Vision OCR → Firestore role check → live dashboard + physical OLED verdict — was **verified running live during this audit** (real heartbeats accepted with HTTP 202, `last_seen` refreshing, SSE connected). The LPR is a **real cloud integration, not a mock**. Role-based authorization is **enforced server-side**. Edge cases the team designed for (camera-before-heartbeat race, bouncy driver, ghost-log manual review, stale-capture cleanup) are genuinely implemented in code, not just documented.

However, the project is **not complete against its own definition**. Of 11 user stories plus 2 extra requirements: **1 is Complete, 10 are Partial, 2 are Missing/Broken in part**. The most significant gaps:

- **Incentive points: entirely missing** (no model, no code, no data) despite being in the project definition.
- **No low-battery or offline alerts beyond the open dashboard** — "notification" is dashboard-only, computed client-side; an admin who isn't watching gets nothing.
- **Admin node-configuration UI/endpoint does not exist** — spots are configured by editing Firestore directly or re-running a seed script; category values are never validated.
- **OCR output is not validated as a plausible plate** (any digits in the image are concatenated, no 7/8-digit check), risking false violations against legitimate drivers.
- **Automated test coverage of the backend's 1,600-line state machine is zero**; one of two Python test files is broken (imports a deleted module).
- **Hardware endpoints are unauthenticated** (MAC-trust only), CORS is `*`, and ESP32 TLS skips certificate validation — acceptable for a course prototype, unacceptable beyond it.

**Overall score: 42/80 → 52.5%.** Prototype: **Ready**. Demo: **Mostly Ready**. Pilot: **Limited**. Production: **Not Ready**.

## 2. Repository and Architecture Overview

### Components detected

| Component | Location | Technology |
|---|---|---|
| Sensor firmware | `ESP32/ParkMeSensorNode/ParkMeSensorNode.ino` (1,634 lines) | ESP32 Arduino, dual-core FreeRTOS, HC-SR04, SSD1306 OLED (low-level driver) |
| Camera firmware | `ESP32/ParkMeCameraNode/ParkMeCameraNode.ino` (597 lines) | ESP32-CAM (AI-Thinker), ESP-NOW receiver, multipart HTTP upload |
| Shared firmware lib | `ESP32/ParkMeCommon/ParkMeCommon.h` (346 lines) | Header-only: enums, ESP-NOW structs, JSON/MAC/HTTP helpers |
| Backend/API | `Backend/main.py` (1,614 lines), `Backend/parking_logic.py` | FastAPI, firebase-admin, google-cloud-vision, SSE |
| Database | Firebase Firestore (cloud) | 5 collections; no SQL, no migrations (schema implicit) |
| LPR | `Backend/main.py:442-468` `extract_license_plate()` | **Real** Google Cloud Vision (`text_detection` + `document_text_detection`) |
| Frontend | `Frontend/` (index.html, app.js 815 lines, style.css) | Vanilla JS, Firebase Auth compat SDK, EventSource SSE |
| Auth | Firebase Authentication + Firestore `users` collection | JWT verified server-side (`main.py:1017-1047`) |
| Config | `ESP32/SECRETS.h` (git-ignored, `SECRETS.example.h` template), `Backend/env` | Constants compiled into firmware |
| Tests | `tests/` (2 Python files), `ESP32/ParkMeFirmwareCompileTests/`, `Unit Tests/` (3 HW sketches) | unittest, static_assert, hardware-in-loop |
| Deployment | `Backend/Dockerfile`, `Backend/cloudbuild.yaml`, `firebase.json`, `Backend/.dockerignore` | Cloud Run (me-west1) + Firebase Hosting |
| Docs | `Documentation/` (overview, local testing, cloud deployment), `ESP32/hardware-upload-guide.md` | Current and code-verified |

### Data flows

- **Sensor → UI:** HC-SR04 (3-sample avg, 500 ms) → `classifyDistanceCm` (≤20 cm occupied) → HTTP heartbeat `POST /api/v1/sensors/heartbeat` (every 20 s + on change) → Firestore `parking_spots` + `parking_logs` → SSE `spot_update` → dashboard card re-render.
- **Camera → authorization:** ESP-NOW trigger → single JPEG capture (2 dummy FIFO flush grabs) → multipart `POST /api/v1/sensors/park` (same frame re-sent up to 3×) → Vision OCR → `vehicles`→`users` lookup → role vs. spot category → WELCOME/DENIED + log write + SSE + OLED display command over `GET /api/v1/displays/stream` (SSE).
- **Auth/role model:** Firebase login → ID token → backend verifies and maps email → Firestore role (`admin`, `student`, `lecturer`, `staff`, `special-needs-driver`). Authorization rule (`main.py:932`): `role == "admin" or role == spot_category`.

### Contradictions between documentation and code (flagged)

1. `POST /api/v1/telemetry/bulk` exists (`main.py:1476-1605`) and older docs describe multi-event offline replay, but **no firmware calls it** — the sensor persists only a single latest unsent state (`ParkMeSensorNode.ino:955-978`).
2. `PARKME_GATE_MAX_CAPTURE_RETRIES` (`SECRETS.example.h:66`) is unused; retries are hardcoded to 3 (`ParkMeCameraNode.ino:392`).
3. `computeOccupiedThreshold()` exists and is compile-tested (`ParkMeCommon.h:71-77`) but is **never called**: `loadCalibration()` hardcodes the threshold to 20.0 cm (`ParkMeSensorNode.ino:980-984`), so calibration does not actually adapt the occupancy threshold (see Story 11).
4. Dead legacy code in the sensor sketch (`publishCurrentState()` `:1170-1206`, `handleDisplayPolling()` `:889-930`) is compiled but unreachable from `loop()`.
5. `LPR_DEDUP_CACHE` (`main.py:162`, written `:896`) is never read — dedup is actually achieved by active-log sentinel checks.

## 3. Commands Executed and Results

| Command | Result | Notes |
|---|---|---|
| `python -m unittest tests.test_backend_parking_logic -v` | ✅ **4/4 pass** (0.001 s) | Real behavior tests: tz-aware comparison, preserve/reject camera-first log, terminal-sentinel rejection |
| `python -m unittest tests.test_backend_database -v` | ❌ **FAILED (errors=1)** | `ModuleNotFoundError`-class failure: imports `_support`, which does not exist; tests the **removed SQLite schema**. Dead test |
| `python -m py_compile Backend/main.py` | ✅ pass | Post-fix syntax valid |
| Live smoke test: uvicorn on scratch port → `GET /docs`, `GET /`, `POST /api/v1/displays/poll` | ✅ 200 / 200 / `{"action":"IDLE"}` | Backend boots, serves frontend locally, display poll works |
| Live hardware session (during audit) | ✅ | Sensor heartbeats `-> 202`, `last_seen` age 2 s after MAC fix, ESP-NOW sensor↔camera acks observed on serial |
| `git check-ignore Backend/serviceAccountKey.json Backend/env ESP32/SECRETS.h Backend/.env` | ✅ all ignored | No secrets tracked by git |
| `grep -c "@media" Frontend/style.css` | 1 media query | Minimal responsive handling |
| Firmware compile-time tests (`ESP32/ParkMeFirmwareCompileTests`) | ✅ by construction | 14+ meaningful `static_assert`s over threshold/battery/classification/parse logic (compile in Arduino IDE to execute; not runnable here) |
| Arduino compilation of both sketches | **Cannot run here** | Compiled successfully on the developer's machine during this session after the `ParkMeConfig.h` include-path fix |

No checks were hidden; the broken database test is reported as Broken below.

## 4. Requirement Traceability Matrix

| ID | User story | Status | Main evidence | Tests | Main gap | Risk |
|---|---|---|---|---|---|---|
| 1 | Real-time availability | **Partial** | `ParkMeSensorNode.ino:1602-1634`, `main.py:502-711`, `app.js:670-681,140-149` | Compile-time asserts only | Offline detection is frontend-computed only; bulk offline replay unused | Medium |
| 2 | LPR access | **Partial** | `main.py:423-468, 830-1015`; real Vision API | None | No plate-format validation; no confidence handling | High |
| 3 | Violation alert | **Partial** | `main.py:994-1001, 1408-1474`; `app.js:683-709` | None | Dashboard-only channel; no ack/resolve states | Medium |
| 4 | Accessible parking | **Partial** | `main.py:117, 1042, 1122`; `app.js:220-238` | None | No dedicated no-space messaging; no tests | Low |
| 5 | Battery & maintenance | **Partial** | `ParkMeSensorNode.ino:1025-1039`, `ParkMeCommon.h:106-117`, `app.js:617` | static_asserts for conversion | **No low-battery threshold or alert anywhere** | Medium |
| 6 | Device access display | **Complete** | `ParkMeSensorNode.ino:400-735, 1462-1485`; `main.py:397-418`; verified live | HW OLED sketch + live session | Physical long-run behavior needs field time | Low |
| 7 | Logs & statistics | **Partial** | `main.py:1133-1186, 1263-1345` | None | No date-range queries; stats scan all logs; retention undocumented | Medium |
| 8 | Sensor-node configuration | **Partial** | Firestore fields via `seed_firestore.py:38-60`; `find_spot_by_value` `main.py:348-360` | None | **No admin config UI/endpoint; category values unvalidated; duplicate MACs unhandled** | High |
| 9 | Offline & failure handling | **Partial** | `ParkMeSensorNode.ino:955-978,1416-1460`; `app.js:195-218`; `parking_logic.py:25-47` | 4 unit tests (ordering logic) | Offline alert exists only while an admin dashboard is open; single-slot offline cache | High |
| 10 | Web GUI | **Partial** | `Frontend/app.js` (whole), `index.html` | None | 1 media query; error states minimal; innerHTML rendering | Medium |
| 11 | Calibration & setup | **Partial** | `ParkMeSensorNode.ino:948-953,1008-1023,980-990,1581-1583` | static_asserts (of an **unused** function) | Threshold hardcoded 20 cm — calibration doesn't adapt detection | Medium |
| R1 | Spot recommendations | **Partial** | `app.js:220-238` | None | Frontend-only, first-alphabetical; criteria undocumented | Low |
| R2 | Incentive points | **Missing** | No evidence anywhere in code/DB/seeds | None | Entire feature absent | High (requirement) |

## 5. Detailed User-Story Review

### Story 1 – Availability

```text
Status: Partial
Evidence:
- ESP32/ParkMeSensorNode/ParkMeSensorNode.ino:992-1006 sampleAverageDistance() (3 samples, 120ms apart, invalid readings excluded)
- ESP32/ParkMeCommon/ParkMeCommon.h:89-96 classifyDistanceCm() (UNKNOWN for invalid/out-of-range, distinct from OCCUPIED)
- Backend/main.py:502-711 receive_heartbeat_data (updates is_occupied, last_seen, battery; broadcasts spot_update)
- Backend/main.py:1053-1131 GET /api/v1/spots (role-filtered availability; non-admins see only their category, plates hidden)
- Frontend/app.js:140-149 isSpotOffline (last_seen > 120s → OFFLINE), :670-681 updateSpotUI, :734-783 5s full-refresh diff
- Live verification: heartbeat -> 202 and last_seen age 2s observed during audit
Explanation:
Detection, stabilization (averaging + UNKNOWN discard), transport, per-spot state with timestamps, live SSE updates,
role filtering, and stale-data flagging all exist and were seen working. Multi-node support is by MAC→spot mapping.
Gaps: (a) staleness is computed only in the browser — the backend never marks a spot unknown, so any future API
consumer would read stale is_occupied as fresh; (b) rapid toggling is smoothed only by 3-sample averaging on the
node plus the backend's 90s bouncy-driver merge — there is no debounce window on state changes themselves;
(c) offline history is lost (single-slot cache; /telemetry/bulk unused).
Risk: Medium
Recommended action:
Compute an `is_stale`/`status=unknown` field server-side in GET /spots and SSE payloads from last_seen, so staleness
is a backend guarantee rather than a client convention; add unit tests for the transition logic.
```

### Story 2 – LPR Access

```text
Status: Partial
Evidence:
- ESP32/ParkMeCameraNode/ParkMeCameraNode.ino:342-460 captureAndUpload() (real capture, FIFO flush, 3 send attempts)
- Backend/main.py:442-468 extract_license_plate() — real Google Vision text_detection + document_text_detection
- Backend/main.py:423-427 _extract_plate_digits() — keeps *all* digits found anywhere in the OCR text
- Backend/main.py:898-938 vehicle→user lookup and role-vs-category decision (role == "admin" or role == spot_category)
- Backend/main.py:832-893 OCR-failure path → UNIDENTIFIED ghost log + manual review (fails closed, not open)
- Backend/main.py:772-828 sentinel checks prevent a late photo overwriting an admin decision
Explanation:
The pipeline is real end-to-end: capture → upload → cloud OCR → registered-vehicle match → role authorization →
distinct WELCOME/DENIED outcomes → display + dashboard. Failure never grants access (unknown/unreadable → denied +
review). Gaps: (a) no plate-format validation — digits from stickers/phone numbers are concatenated, so a legitimate
plate can be misread into a nonexistent one (false violation) or, worst case, into a different registered plate
(false authorization); Israeli plates are exactly 7–8 digits and this is not enforced; (b) Vision confidence values
are ignored; (c) normalization is digits-only (consistent, but see (a)); (d) LPR_DEDUP_CACHE (main.py:162,896) is
write-only dead code.
Risk: High
Recommended action:
In _extract_plate_digits, extract contiguous digit groups (allowing -/space separators) and accept only 7–8 digit
results; otherwise route to the existing UNIDENTIFIED review flow. Add unit tests with realistic OCR text samples.
```

### Story 3 – Violation Alert

```text
Status: Partial
Evidence:
- Backend/main.py:918-940 violation determination (unregistered plate or role mismatch), :940 evidence capture_base64
- Backend/main.py:994-1001 log_event SSE broadcast (admins only — main.py:110-119 role-gates all log events)
- Backend/main.py:1408-1474 reject flow attaches evidence image permanently to the log
- Backend/main.py:230-245 GET /logs/{id}/capture serves evidence; app.js:701-708 realtime "Show Picture" button
- Backend/main.py:595-599 bouncy-driver reversal broadcasts log_aborted; app.js:432-445 rewrites the log line
Explanation:
Violations are recorded with spot, timestamp, plate (or UNIDENTIFIED/REJECTED), reason encoded in message type, and
photo evidence. Ordinary users never receive log events (server-side role gate on both SSE and GET /logs). Duplicates
are structurally limited by the one-active-log-per-spot design. Gaps: (a) the only channel is the dashboard — no
email/push/webhook, so an absent admin is never notified; (b) no new/acknowledged/resolved lifecycle on violations;
(c) alerts are fire-and-forget into in-memory queues — a backend restart loses undelivered events (records survive
in Firestore).
Risk: Medium
Recommended action:
Add one out-of-band channel (email via a Cloud Function on parking_logs writes, or FCM push) and an
`acknowledged_by/at` field on violation logs surfaced in the admin UI.
```

### Story 4 – Accessible Parking

```text
Status: Partial
Evidence:
- Backend/seed_firestore.py:47-48 category "special-needs-driver" on spot B1; users seed role "special-needs-driver"
- Backend/main.py:1042 is_special_needs derived from role; :1122 spots filtering; :115-118 SSE filtering
- Backend/main.py:932-938 authorization: non-matching role in accessible spot → violation (server-side)
- Frontend/app.js:220-238 renderRecommendation (only free + non-offline spots the user is allowed to see)
Explanation:
Accessible parking is a first-class category. A student cannot be authorized in an accessible spot (role mismatch →
violation) and cannot even see accessible spots in the UI (server-side filter, not just hidden buttons). The
recommendation banner for an accessible driver draws only from their permitted, online, free spots, and shows an
explicit "No verified free spots" message otherwise (app.js:229-233). Offline accessible spots are excluded from
recommendations. Gaps: role model is single-role — an accessible driver has no base role, which matches the seeds
but means "only where base role permits" from the conceptual matrix is unimplemented (reported as a requirements
ambiguity, not invented); no tests.
Risk: Low
Recommended action:
Document the single-role decision explicitly; add an authorization unit test matrix covering all role×category pairs.
```

### Story 5 – Maintenance (Battery)

```text
Status: Partial
Evidence:
- ESP32/ParkMeSensorNode/ParkMeSensorNode.ino:1025-1033 readBatteryVoltage (analogReadMilliVolts × divider ratio)
- ESP32/SECRETS.example.h:32-34 named constants (3.20V empty, 4.20V full, ratio 2.0 — not magic numbers)
- ESP32/ParkMeCommon/ParkMeCommon.h:106-117 batteryPercentFromVoltage (clamped 0–100; static_assert-tested)
- Backend/main.py:132-135 HeartbeatPayload battery_level validated ge=0 le=100 (impossible values → 422)
- Frontend/app.js:617 admin card shows "🔋 Battery: N%" per node; staleness covered by the 2-min offline marker
Explanation:
Sampling, conversion, transport with node identity + timestamp, storage, and per-node admin display all exist.
Gaps: (a) there is NO low-battery threshold, warning, or alert anywhere in backend or frontend — the story's core
promise ("replace batteries before a node goes offline") is unmet; (b) live reading was 0% in this audit because the
battery pin is unwired on the bench — plausible-but-wrong values are accepted (only <0/>100 rejected).
Risk: Medium
Recommended action:
Add a LOW_BATTERY_THRESHOLD (e.g. 20%) check in receive_heartbeat_data that emits a rate-limited admin log_event,
plus a red battery badge in createSpotCard. Small, self-contained change.
```

### Story 6 – Device Access Display

```text
Status: Complete
Evidence:
- ESP32/ParkMeSensorNode/ParkMeSensorNode.ino:573-645 display init with I2C scan + address fallback + error handling
- ESP32/ParkMeSensorNode/ParkMeSensorNode.ino:1462-1485 checkSharedDisplayCommand (server verdicts rendered on Core 1)
- Backend/main.py:1004-1010 queue_display_command "Welcome <name>" / "Access denied" with hold_ms durations
- ESP32/ParkMeSensorNode/ParkMeSensorNode.ino:680-699 priority model (server > local camera > idle) and expiry
- Unit Tests/HW_OLED_SSD1306_I2C_Test + live audit session (screen updates observed on serial)
Explanation:
All checks pass: init/error handling, authorized vs denied distinguishable, timed holds (5s welcome, 25s reject),
correct replacement of previous messages, error paths never display Welcome (failure paths show "Photo failed" /
"Admin review"), and rendering is non-blocking (display on Core 1, network on Core 0, mutex-protected handoff).
Verified live during the audit.
Risk: Low
Recommended action:
None functionally; extended-runtime burn-in on real hardware remains prudent before demo day.
```

### Story 7 – Logs and Statistics

```text
Status: Partial
Evidence:
- Backend/main.py:955-967 historical parking_logs (entry/exit, role snapshot, violation flag) — history ≠ current state
- Backend/main.py:15-32 IL-timezone handling with Windows fallback; timestamps everywhere
- Backend/main.py:1263-1345 usage-stats: peak hour, busiest spot, avg duration, outcome counters — from stored logs
- Backend/main.py:1133-1186 GET /logs (admin-only, DESC, limit 50, anomalies-only by explicit design comment :1174-1178)
- Frontend/app.js:151-193 stats cards; :683-709 security log rendering
Explanation:
Real historical records feed real aggregate statistics, admin-gated server-side. Gaps: (a) no query filters — no
spot/zone/category/date-range parameters on /logs; (b) usage-stats reads the ENTIRE parking_logs collection per
request (main.py:1266) — unbounded cost as history grows; (c) fixed limit 50, no pagination; (d) retention policy
absent — plates and violation photos accumulate indefinitely (also a privacy issue, §13).
Risk: Medium
Recommended action:
Add ?from/?to&spot_id query params to /logs, a date-window cap on usage-stats aggregation, and a documented
retention policy (e.g., TTL policy on parking_logs).
```

### Story 8 – Configuration

```text
Status: Partial
Evidence:
- Backend/seed_firestore.py:42-55 nodes mapped to spots with category via sensor_mac/camera_mac fields
- Backend/main.py:348-365 find_spot_by_value (MAC→spot resolution, legacy field fallback, .limit(1))
- Configuration persistence: Firestore documents (survives restart by nature)
- During audit: C1 was configured by writing MACs directly to Firestore via an ad-hoc script — no product surface exists
Explanation:
Mapping and persistence exist, and category changes do affect both authorization (main.py:932) and visibility
(main.py:1122). But: (a) there is NO admin-facing configuration endpoint or UI — configuration means editing
Firestore in the console or re-running the seeder (which WIPES all spots, seed_firestore.py:40); (b) category values
are never validated anywhere — a typo like "studnet" silently makes a spot invisible to everyone but admins and
denies all drivers; (c) duplicate MAC mappings resolve arbitrarily to the first query hit; (d) firmware
PARKME_GATE_SPOT_ID and the server's MAC→spot mapping can silently disagree — the OLED would show "Spot C1" while
the backend logs events against whatever spot the MAC maps to (no cross-check on either side).
Risk: High
Recommended action:
Add PUT /api/v1/admin/spots/{id} (admin-gated) with a category enum whitelist and MAC-uniqueness check; have the
heartbeat response echo the resolved spot_id so firmware can log a mismatch warning.
```

### Story 9 – Offline Handling

```text
Status: Partial
Evidence:
- ESP32/ParkMeCameraNode/ParkMeCameraNode.ino:245-253 maintainWiFi (bounded 5s-interval retry, non-blocking)
- ESP32/ParkMeSensorNode/ParkMeSensorNode.ino:1416-1460 networkTask (WiFi-down → flag + 1s sleep; SSE backoff 3→30s)
- ESP32/ParkMeSensorNode/ParkMeSensorNode.ino:955-978 NVS-persisted pending telemetry, flushed on reconnect
- Backend: last_seen written on every heartbeat (main.py:611-614)
- Frontend/app.js:195-218 offline detection (>120s) with one admin toast per transition + recovery toast; :226 offline
  spots excluded from recommendations; :570-572 OFFLINE card state distinct from occupied/free
- Backend/parking_logic.py:25-47 + 4 passing unit tests: out-of-order/stale-event protection for the heartbeat race
Explanation:
Firmware survives Wi-Fi loss without crashing (verified on the bench today: sensing + ESP-NOW continued while WiFi
was down), retries are bounded, offline spots are visibly untrusted and excluded from recommendations, recovery is
signaled, and duplicate offline toasts are prevented by the offlineSpotIds set. Power loss is correctly inferred
only via missed heartbeats. Gaps: (a) the offline "notification" exists ONLY inside an open admin dashboard —
detection runs in the browser (app.js:118-124), so no admin online = no alert ever, and the backend itself never
flags staleness; (b) the offline cache holds exactly one state without a timestamp — event history during outages
is lost and /telemetry/bulk (main.py:1476) is dead capacity; (c) sensor initial WiFi connect happens once at boot
(12s window) with recovery delegated to the SDK's setAutoReconnect (ParkMeSensorNode.ino:1585) — weaker than the
camera's explicit retry; (d) camera's one-capture-per-cycle latch means a car arriving during camera downtime is
never photographed even after recovery (ParkMeCameraNode.ino:210, reset only on spot-free).
Risk: High
Recommended action:
Move staleness to the backend (periodic task or computed field marking spots unknown after 2 min, emitting one
admin log_event); timestamp the cached telemetry and use /telemetry/bulk for true replay.
```

### Story 10 – Web GUI

```text
Status: Partial
Evidence:
- Frontend/index.html + app.js: login, role badge, live spot grid, admin panel, toasts, connection-status dot
- app.js:399-450 SSE with auto-reconnect; :734-783 polling safety net; API failure → console.error + stale UI
- Server-side admin gating (main.py:1257-1260); non-admin data minimization in /spots (plates stripped, main.py:1122-1130)
- Frontend/style.css: exactly 1 @media query (grep count) — minimal responsive design
- app.js:604,698 innerHTML rendering of backend-derived strings
Explanation:
The GUI is real, connected to live data, role-aware, and separates admin functionality with true backend
enforcement. Auto-login, logout cleanup, pending-button states, and image error handling (disabling review buttons
on failed image load, app.js:635) show care. Gaps: (a) responsiveness is minimal for an "on the go" use case;
(b) API failures mostly log to console rather than showing user-visible error states (fetchSpots/fetchLogs catch →
console.error only); (c) status is color-coded but does carry text labels (OFFLINE/EMPTY/plate) — partial
accessibility; no keyboard/ARIA consideration; (d) innerHTML with server-derived strings is an XSS vector if any
upstream value (e.g., a future free-text field) becomes attacker-controlled — currently low exposure since plates
are digits-only.
Risk: Medium
Recommended action:
Add a visible "backend unreachable" banner on fetch failures, more responsive breakpoints for mobile, and switch
log/plate insertion to textContent.
```

### Story 11 – Calibration

```text
Status: Partial
Evidence:
- ESP32/ParkMeSensorNode/ParkMeSensorNode.ino:948-953 + 1208-1223 intentional entry (button at boot, or 4s hold)
- :1008-1023 runCalibrationMode — 15 samples, fails safely keeping previous baseline on invalid readings
- :986-990 saveCalibration → NVS Preferences; :980-984 loadCalibration on boot (persists across restart; per-node by nature)
- :1581-1583 boot-time invocation; serial success/failure feedback with stored values
Explanation:
Entry, multi-sampling, invalid-reading safety, persistence, per-node values, restart recovery, feedback, and
recalibration all check out. The critical gap: the calibrated baseline is used ONLY for the free-distance upper
limit (currentFreeDistanceLimitCm :1147-1151). The occupancy threshold itself is hardcoded to 20.0f in BOTH
loadCalibration and saveCalibration, while the purpose-built computeOccupiedThreshold(baseline, delta, min) sits
unused (ParkMeCommon.h:71-77 — ironically covered by compile-time tests). Result: calibration does not adapt vehicle
detection to different parking-space dimensions, which is the story's stated purpose.
Risk: Medium
Recommended action:
In load/saveCalibration set occupiedThresholdCm = computeOccupiedThreshold(baselineDistanceCm,
PARKME_SENSOR_OCCUPIED_DELTA_CM, PARKME_SENSOR_MIN_THRESHOLD_CM); verify on hardware with two different baselines.
```

## 6. Additional Requirements

### Spot Recommendations

```text
Status: Partial
Evidence:
- Frontend/app.js:220-238 renderRecommendation — filters currentSpots to !is_occupied && !isSpotOffline, sorts by id,
  recommends the first; explicit empty-state message
- Input data is already role-filtered by GET /spots (main.py:1109-1130), so permits and accessible authorization are
  respected transitively
Explanation:
A recommendation exists and respects availability, role/permit, accessible authorization, offline exclusion, and
occupied exclusion — all the required signals. But it is frontend-only (no endpoint), the criterion is
first-by-alphabetical-id (undocumented, no distance/priority notion), and nothing tests it.
Risk: Low
Recommended action:
Document the selection rule; optionally move it into GET /spots as a `recommended: true` flag so all clients agree.
```

### Incentive Points

```text
Status: Missing
Evidence:
- Exhaustive search: no "points" field in seed_firestore.py users, no points logic in main.py, no UI in app.js.
  The only references are a stale doc claim ("role and points" in the old PROJECT_STATE doc) and the broken legacy
  SQLite test (tests/test_backend_database.py:47 expects users.points) — both referring to the removed architecture.
Explanation:
No points model, earning rules, storage, display, or abuse prevention exist in the current Firestore-based system.
Risk: High (it is a stated project-definition requirement with zero implementation)
Recommended action:
Either implement a minimal version (points field on users; award on authorized session close in the heartbeat exit
path; display in /users/me and the header badge; idempotency via log-id-keyed transactions) or formally descope it
in the project documentation before submission.
```

## 7. Role and Authorization Review

**Actual policy in code** (`main.py:932`): `is_violation = False` iff `snapshot_role == "admin"` **or** `snapshot_role == spot_category`. Applied identically for visibility (`main.py:1122`, `:115-118`).

| Role | Student zone | Lecturer zone | Staff zone | Accessible zone |
|---|---:|---:|---:|---:|
| Student | ✅ Allowed | ❌ Violation | ❌ Violation | ❌ Violation |
| Lecturer | ❌ Violation | ✅ Allowed | ❌ Violation | ❌ Violation |
| Staff | ❌ Violation | ❌ Violation | ✅ Allowed | ❌ Violation |
| special-needs-driver | ❌ Violation | ❌ Violation | ❌ Violation | ✅ Allowed |
| Admin | ✅ | ✅ | ✅ | ✅ |

- Enforcement is **server-side** at both decision time (park event) and read time (spots/logs/stats/accept/reject/SSE). Frontend hiding is not relied upon. ✅
- **Requirements gap (not invented):** the conceptual model in the audit instructions implies permits layered on base roles ("accessible permit + base role"). The implementation is single-role — a special-needs driver has no base-role rights, and "staff in lecturer zone" is flat-denied rather than "according to configured policy". No configurable policy exists.
- Hardware endpoints (`/sensors/heartbeat`, `/sensors/park`, `/displays/*`, `/telemetry/bulk`) require **no authentication** — identity is a self-reported MAC (see §13).

## 8. Data Model and Database Review

Firestore (schemaless — constraints are code-enforced only):

| Entity | Collection / location | Keys & notes |
|---|---|---|
| User | `users` (doc id = email) | role string unvalidated; no enum constraint |
| Vehicle/plate | `vehicles` (doc id = plate digits) | 1 plate → 1 user; a user may have many |
| Parking space + node + current occupancy + battery + calibration-adjacent review state | `parking_spots` (doc id = spot id) | **One doc mixes** static config (macs, category), live state (is_occupied, battery, last_seen), and transient review fields — acceptable at this scale, but current-vs-config is not separated |
| Historical event / access attempt / violation | `parking_logs` (auto-id) | entry/exit timestamps, is_violation, sentinel plates encode workflow state, base64 evidence embedded |
| Temporary capture | `spot_captures` (doc id = sanitized spot id) | Deleted on spot-free (main.py:617-619) — good hygiene |
| Sensor reading (raw), Notification, Points transaction | — | **Not modeled** (readings are ephemeral; notifications are transient SSE; points absent) |

Findings:
- **No composite indexes needed by design** — active-log queries filter then sort in Python (`main.py:171-189`). Correct but O(active logs).
- **Duplicate-event prevention** is behavioral (one active log per spot + sentinel checks), not constraint-based; two writers could theoretically create two active logs (no transactions used).
- **1 MiB Firestore doc limit** vs. base64 VGA JPEGs (~40–130 KB): safe margin, but multiple evidence images per log would not be.
- **Sentinel plates in `license_plate`** (UNIDENTIFIED/REJECTED/…) overload a data field as a state machine — effective, but any future exact-plate analytics must exclude sentinels; documented in PROJECT_OVERVIEW.
- No migrations exist (schemaless); `seed_firestore.py:40` **wipes spots on every run** — operationally dangerous (during this audit it erased manually-set MACs).

## 9. API Review

| Method | Path | Purpose | Auth | Roles | Input validation | Main response |
|---|---|---|---|---|---|---|
| POST | `/api/v1/sensors/heartbeat` | Node state+battery | **None (MAC-trust)** | n/a | Pydantic (`battery` 0–100, bools) | 202 JSON |
| POST | `/api/v1/sensors/park` | Photo upload → decision | **None (MAC-trust)** | n/a | Form+UploadFile; **no size/type limit** | Gate JSON (WELCOME/DENIED) |
| POST | `/api/v1/telemetry/bulk` | Offline replay | **None** | n/a | Pydantic list | 202 JSON (unused by firmware) |
| GET | `/api/v1/displays/stream` | LCD SSE | **None** (display_id only) | n/a | non-empty check | SSE |
| POST | `/api/v1/displays/poll` | LCD poll fallback | **None** | n/a | Pydantic | JSON command/IDLE |
| POST | `/api/v1/displays/result` | LCD ack | **None** | n/a | Pydantic | 200 |
| GET | `/api/v1/stream` | Dashboard SSE | Firebase JWT **as query param** | all (role-filtered events) | token verified | SSE |
| GET | `/api/v1/users/me` | Profile/role | Bearer JWT | all | header parse | JSON (no points field) |
| GET | `/api/v1/spots` | Availability | Bearer JWT | role-filtered payloads | — | JSON |
| GET | `/api/v1/logs` | Security log | Bearer JWT | **admin only** (403) | — | JSON (limit 50) |
| GET | `/api/v1/admin/usage-stats` | Statistics | Bearer JWT | **admin only** | — | JSON |
| GET | `/api/v1/captures/{spot_id}` | Review image | **None** | — | spot id sanitized (path-traversal safe, main.py:211-213) | image/jpeg |
| GET | `/api/v1/logs/{log_id}/capture` | Evidence image | **None** | — | Firestore doc id | image/jpeg |
| PUT | `/api/v1/sensors/accept` | Resolve ghost log | Bearer JWT | **admin only** | Pydantic | JSON |
| PUT | `/api/v1/sensors/reject` | Reject ghost log | Bearer JWT | **admin only** | Pydantic | JSON |

Cross-cutting: CORS `allow_origins=["*"]` (`main.py:79-85`); no rate limiting anywhere; no pagination; consistent JSON errors via HTTPException; OpenAPI at `/docs` auto-accurate. **Notable:** the two image endpoints require no auth — anyone with a spot/log id can fetch violation photos (personal data). SSE token in the query string can end up in access logs.

## 10. LPR Review

Pipeline (all steps traced): capture (`ParkMeCameraNode.ino:342-379`, fresh-frame guarantee via double FIFO flush) → transmission (multipart, same-frame ×3 retry; **plaintext HTTP locally / TLS-without-verification in cloud**) → detection+OCR (**real Vision API**, two-detector fallback, `main.py:442-468`) → normalization (digits-only) → confidence (**not evaluated**) → vehicle lookup (doc-id get) → role lookup → zone authorization → decision/log/notify/display (all present).

- **Real vs. mock:** unambiguously real — no hardcoded plates, no stub paths; failures produce `UNIDENTIFIED` review flow (fails closed).
- **False-positive safety:** weak — see Story 2 (digit concatenation, no length gate, no confidence gate).
- **Upload hygiene:** no image size/type validation (`file.read()` unbounded, `main.py:750`); Cloud Run's 32 MB request cap is the only backstop. No temp files (memory-only) — cleanup non-issue.
- **Privacy/retention:** plates + photos stored indefinitely in `parking_logs`; temporary review images are properly deleted on spot-free. Retention undocumented (§13).
- **Timeouts:** Vision call has no explicit timeout (relies on client defaults) inside a synchronous `def`-style flow within an async endpoint — a hung call stalls that request worker.

## 11. Firmware and Hardware Review

| Expected hardware | Code/doc status |
|---|---|
| ESP32 (sensor) | ✅ Pins in SECRETS (trig 5, echo 18, battery 34, button 0); live-verified |
| HC-SR04 | ✅ Logic verified live (62 cm readings). ⚠️ **Echo is 5 V; no voltage-divider protection is documented anywhere** — flagged, Cannot Verify wiring |
| ESP32-CAM | ✅ AI-Thinker pin map (`ParkMeCameraNode.ino:12-28`); PSRAM-adaptive framesize; flash LED GPIO4 |
| Li-ion battery + divider | ✅ Constants (3.2–4.2 V, ratio 2.0); ⚠️ bench reading 0% (pin unwired) — physical measurement **Cannot Verify** |
| Display | ✅ SSD1306 OLED, I2C scan with address fallback, column-offset config; live-verified |

Other checks: unique identity = WiFi MAC (spoofable, §13); WiFi provisioning = compiled constants (reflash to change; no captive portal); **no watchdog, no deep-sleep/power-saving strategy** (500 ms sampling + always-on WiFi contradicts battery operation — battery life will be hours, not weeks); **no OTA/firmware-update path**; ESP-NOW envelope validated by magic+version (`ParkMeCommon.h:230-236`) but unencrypted/unauthenticated (`encrypt = false`); `ParkMeConfig.h` uses machine-absolute include paths (fixed for this machine during the session — breaks per-clone, documented in-file). Camera one-shot-per-cycle latch: see Story 9(d). Physical wiring, echo-pin protection, and real battery curves remain **Cannot Verify** without bench evidence.

## 12. Reliability and Failure Scenarios

Traced scenarios (evidence in Stories 1/2/9 unless noted):

1. **Power, no Wi-Fi:** sensing/OLED/ESP-NOW continue (verified live); single-slot NVS cache; SDK-dependent reconnect. Handled with caveats.
2. **Sensor loses power:** no heartbeat → frontend marks offline after 120 s; recommendation exclusion. Handled (browser-only alert).
3. **Backend unavailable:** camera retries ×3 then latches until spot-free (gap); sensor queues last state. Partially handled.
4. **Database unavailable:** unhandled — Firestore exceptions propagate as 500s; no retry/circuit-breaker.
5. **Camera unavailable:** heartbeat-first ghost log → 30 s `missing_photo` → blind admin review; stale-capture wipe on spot-free (`main.py:616-619`). Handled well.
6. **LPR timeout:** caught by broad except → UNIDENTIFIED review (`main.py:465-468`); but no explicit timeout bound. Partially handled.
7. **Unknown plate:** denied + violation + evidence. Handled.
8. **Invalid distance:** STATE_UNKNOWN → skipped, never transmitted (`ParkMeSensorNode.ino:1623-1631`). Handled.
9. **Impossible battery:** 422 via Pydantic bounds; in-range-but-wrong accepted. Partially handled.
10. **Frontend can't reach API:** SSE auto-reconnect 3 s; fetch failures console-only (gap). Partially handled.
11. **Two nodes, same spot / duplicate MACs:** first-match wins silently. Not handled.
12. **Old data after newer data:** `should_preserve_recent_active_log` guards the heartbeat/camera race (unit-tested ✅); but flushed offline telemetry carries no original timestamp. Partially handled.

Other reliability notes: in-memory SSE registries mean restart drops all streams (clients reconnect — acceptable); `sse_clients.remove()` in generator `finally` can race concurrent broadcasts (low likelihood at this scale); IL-timezone handled with Windows fallback (`main.py:15-32`); Vision + Firestore calls are blocking inside async handlers — under concurrent uploads the event loop stalls (single-instance deploy masks this).

## 13. Security and Privacy Review

| Check | Finding | Risk |
|---|---|---|
| Secrets in git | ✅ `serviceAccountKey.json`, `env`, `SECRETS.h` all verified git-ignored; `.dockerignore` added this session keeps them out of images | — |
| Default credentials | ⚠️ Seeded `password123` for all users incl. admin (`create_auth_users.py:12-16`) — fine for demo, must rotate for anything public | Medium |
| Password hashing | ✅ Delegated to Firebase Auth | — |
| Token validation/expiry | ✅ `verify_id_token` with 10 s skew (`main.py:1022`); 1 h Firebase expiry | — |
| Server-side role checks | ✅ Everywhere user-facing (`get_current_admin`, filtered SSE) | — |
| **Hardware endpoint auth** | ❌ None. Anyone on the network (or Internet, once on Cloud Run with `--allow-unauthenticated`) can POST fake heartbeats/photos for any MAC, occupy/free spots, spam ghost logs. The `ESP32_HMAC_SECRET` in `env.example:12` suggests a planned HMAC scheme that was **never implemented** | **High** |
| **Capture endpoints auth** | ❌ `GET /captures/{spot}` and `GET /logs/{id}/capture` are public — violation photos (personal data) retrievable by id | High |
| SSE token in URL | ⚠️ `?token=<JWT>` (`app.js:405`) — can persist in server/proxy logs | Medium |
| Injection safety | ✅ Firestore SDK (no raw queries); spot-id sanitization for doc paths (`main.py:193-195`) | — |
| Upload validation | ❌ No content-type/size check on images | Medium |
| Logs vs. sensitive data | ⚠️ OCR raw text (may contain bystander text) and plates logged at INFO (`main.py:424`) | Low/Medium |
| Image/plate retention | ❌ Indefinite, undocumented | Medium |
| Transport | ⚠️ Local = plaintext HTTP by design; cloud = HTTPS but ESP32 `setInsecure()` skips cert validation (MITM-able) | Medium |
| Node impersonation | ❌ Trivial (self-reported MAC) | High (overlaps hardware auth) |
| Debug endpoints | ✅ Only `/docs` (FastAPI default) — harmless read-only schema | — |
| CORS | ⚠️ `*` with credentials — must be locked to hosting origin for production (documented in deployment guide) | Medium |
| Stack traces | ✅ HTTPExceptions with clean messages; FastAPI default 500 handler doesn't leak traces to clients | — |
| Dependencies | ✅ Recent, floor-pinned (`requirements.txt`); no known-critical pins spotted | Low |
| Privacy documentation | ❌ None (what's collected, why, how long) | Medium |

## 14. Test Quality and Coverage

| Area | Coverage |
|---|---|
| Sensor threshold/calibration/battery/classification/parse logic | ✅ Strong **compile-time** static_asserts (`ParkMeFirmwareCompileTests.ino`) — including, ironically, the unused `computeOccupiedThreshold` |
| Heartbeat/camera race ordering | ✅ 4 real unit tests, all passing (`tests/test_backend_parking_logic.py`) |
| Hardware bring-up | ✅ 3 documented HW sketches with PASS/FAIL serial output (`Unit Tests/`) |
| Occupancy state transitions (backend), review flow, accept/reject, bouncy driver, violations, stats, auth/roles, plate normalization, LPR failure, offline detection, recommendations, frontend states, E2E | ❌ **Zero automated coverage** — `main.py` (1,614 lines) and `app.js` (815 lines) are untested |
| Legacy | ❌ `tests/test_backend_database.py` is **Broken** (missing `_support` module; targets deleted SQLite schema) — misleading dead weight |

No flaky or always-pass tests found; no real personal data in test fixtures; no CI workflow exists to run any of it.

## 15. Documentation and Deployment Review

✅ Strong and current (rewritten this month, code-verified): `Documentation/PROJECT_OVERVIEW.md` (architecture, DB, timings, edge cases), `LOCAL_TESTING_GUIDE.md` (copyable commands incl. firewall + verification checklist), `CLOUD_DEPLOYMENT_GUIDE.md` (deploy commands, 15-item troubleshooting, SECRETS.h checklist), `ESP32/hardware-upload-guide.md` (flashing incl. ESP32-CAM FTDI/IO0), `Unit Tests/` docs, seed/default users documented. Deployment code fixed this session (conditional static mount, `.dockerignore`, cloudbuild flags).
Gaps: ❌ no wiring diagram (pin table exists in SECRETS but no HC-SR04 5V-echo warning); ❌ no privacy/retention statement; ❌ no formal demo-day script; ⚠️ known limitations exist in PROJECT_OVERVIEW §6.4 but not as a single honest "limitations" page.

## 16. Missing, Partial, and Broken Features

- **Missing:** incentive points (entire feature); low-battery alerts; admin node-configuration endpoint/UI; backend-side staleness marking; out-of-band notifications; HMAC device auth (env var exists, code doesn't); retention policy; watchdog/deep-sleep/OTA; privacy docs.
- **Broken:** `tests/test_backend_database.py` (dead import, dead schema).
- **Partial (highest-impact):** plate validation (Story 2); calibration threshold not actually calibrated (Story 11); offline history single-slot + unused bulk endpoint (Story 9); camera capture latch after failure (Story 9); category validation (Story 8); usage-stats full-collection scan (Story 7).
- **Dead code:** `LPR_DEDUP_CACHE`, `publishCurrentState()`, `handleDisplayPolling()`, `PARKME_GATE_MAX_CAPTURE_RETRIES`, `ParkMeLcd/` legacy driver, `computeOccupiedThreshold()` (unused but should be *used*, not deleted).

## 17. Prioritized Fix Plan

### P0 – Must fix before any demo
*(No build/start/main-flow blockers exist — the system runs and was demonstrated live today. Two items qualify as P0 because they can corrupt a live demo:)*

1. **Plate-format validation (false violations against legitimate drivers).**
   Requirement: Story 2. Files: `Backend/main.py` (`_extract_plate_digits`), new tests in `tests/`.
   Approach: extract contiguous digit groups (allow `-`/space separators), accept only 7–8 digits, else return "" → existing review flow. Tests: OCR-text fixtures (clean plate, dashed plate, bumper-sticker noise, short fragment). Complexity: **Small**. Blockers: none.
2. **Seeder data-loss guard.** `seed_firestore.py:40` wipes `parking_spots` including hand-set MACs (bit us during this audit).
   Files: `Backend/seed_firestore.py`. Approach: `--wipe` flag required for deletion; default merges/updates. Tests: dry-run assertion. Complexity: **Small**.

### P1 – Must fix before course submission or pilot

3. **Incentive points — implement minimally or formally descope** (stated requirement, currently Missing). Files: `main.py` (award on authorized exit in heartbeat path; expose in `/users/me`), `seed_firestore.py`, `app.js` (badge). Idempotency: transaction keyed by log id. Tests: award-once semantics. Complexity: **Medium**.
4. **Backend-side offline detection + low-battery alerts** (Stories 5/9): computed staleness in `/spots`+SSE, threshold check in heartbeat, rate-limited admin `log_event`s. Files: `main.py`, `app.js`. Complexity: **Medium**.
5. **Hardware-endpoint authentication:** implement the planned HMAC (`ESP32_HMAC_SECRET`) — signature header over body+timestamp, verified on `/sensors/*` & `/telemetry/*`; also require auth on the two capture-image endpoints. Files: `main.py`, both `.ino`, `ParkMeCommon.h`, `SECRETS.example.h`. Complexity: **Medium/Large**. Blocker: reflash both boards.
6. **Backend state-machine tests:** heartbeat/park/accept/reject/bouncy/review-timeout against a Firestore fake. Files: new `tests/test_main_flows.py`, refactor `get_firestore_db` injection. Complexity: **Large** (highest value per audit rules).
7. **Use calibration for the threshold** (Story 11 core purpose): wire `computeOccupiedThreshold` into load/save. Files: `ParkMeSensorNode.ino:980-990`. Complexity: **Small**. Blocker: hardware re-verification.
8. **Delete `tests/test_backend_database.py`** (Broken, misleading). Complexity: **Small**.
9. **Admin spot-configuration endpoint** with category whitelist + MAC uniqueness (Story 8). Files: `main.py`, optional `app.js` form. Complexity: **Medium**.
10. **Merge `origin/Amir_after_camera_buffer_fix`** (upload-abort on spot-free) so tested code = presented code. Complexity: **Small** (one-commit merge + retest).

### P2 – Important improvements

11. Offline telemetry with timestamps via the existing `/telemetry/bulk` (sensor-side ring buffer). `ParkMeSensorNode.ino`, `ParkMeCommon.h`. **Medium**.
12. Camera capture retry after WiFi recovery (unlatch on recovery while spot still occupied). `ParkMeCameraNode.ino`. **Small**.
13. Sensor explicit WiFi reconnect in `networkTask` (don't rely on SDK auto-reconnect alone). **Small**.
14. Visible frontend error banner on API failure; textContent instead of innerHTML for dynamic strings. `app.js`. **Small**.
15. `/logs` date-range+spot filters; usage-stats windowing; upload size/type validation; SSE token out of URL where feasible; violation ack/resolve lifecycle; remove dead code (`LPR_DEDUP_CACHE`, legacy sensor functions). **Small–Medium** each.
16. CI workflow (GitHub Actions: unittest + py_compile + arduino-cli compile). **Medium**.

### P3 – Optional enhancements

17. Mobile-responsive polish + accessibility (ARIA, keyboard); charts for stats; deep-sleep power strategy (architectural — conflicts with SSE display, needs design); OTA updates; email/push notification channel; privacy/retention page; wiring diagram with HC-SR04 divider note.

## 18. Scores and Readiness Assessment

| # | Category | Score /5 | Rationale (one line) |
|---|---|---:|---|
| 1 | Real-time availability | 4 | Works live end-to-end; staleness client-side only, no tests |
| 2 | LPR & access control | 3 | Real Vision pipeline, fails closed; no plate/confidence validation |
| 3 | Violation alerts | 3 | Rich records + realtime evidence; dashboard-only channel, no lifecycle |
| 4 | Accessible parking | 3 | True category with server-side enforcement; single-role model, untested |
| 5 | Battery & maintenance | 2 | Measured/displayed; **no alerting**, bench value unverified |
| 6 | Device access display | 4 | Complete, priority-safe, dual-core, live-verified; minor field-burn-in risk |
| 7 | Logs & statistics | 3 | Real history + aggregates; no filtering/pagination/retention |
| 8 | Node configuration | 2 | Firestore-only config, no UI/validation, silent conflicts |
| 9 | Offline handling | 3 | Solid firmware resilience + UI staleness; alerts require open dashboard, history lost |
| 10 | Web GUI | 3 | Functional, role-aware, live; weak responsive/error/accessibility |
| 11 | Calibration | 3 | Full mode + persistence; **doesn't drive the threshold it exists for** |
| 12 | Recommendations | 2 | Present with correct exclusions; frontend-only, trivial criterion |
| 13 | Incentive points | 0 | Not implemented |
| 14 | Security & privacy | 2 | Good secret hygiene + server-side roles; unauthenticated device/image endpoints, no retention |
| 15 | Testing | 1 | 4 good unit tests + compile asserts vs. an untested 1,600-line core; one broken file |
| 16 | Documentation & deployment | 4 | Current, code-verified, copyable; missing wiring/privacy/demo-script |

**Final percentage: 42 / 80 = 52.5%**

| Level | Verdict |
|---|---|
| Prototype readiness | **Ready** |
| Demo readiness | **Mostly Ready** (P0 items 1–2 recommended first; hotspot rehearsal per deployment guide) |
| Pilot readiness | **Limited** (device auth, alerts, config UI, tests required) |
| Production readiness | **Not Ready** |

## 19. Final Verdict

1. **Does the repository implement the ParkMe project definition?** Substantially but incompletely — the core IoT parking loop is real and working; auxiliary requirements (points, alerts beyond the dashboard, config UI) are missing.
2. **Complete stories:** Story 6 (Device Access Display).
3. **Partial stories:** 1, 2, 3, 4, 5, 7, 8, 9, 10, 11, plus Recommendations.
4. **Missing/Broken:** Incentive Points (Missing); `tests/test_backend_database.py` (Broken); low-battery alerting and admin config surface (missing sub-features of 5/8).
5. **Does the main end-to-end flow work?** **Yes — verified live during this audit** (sensor → heartbeat 202 → Firestore → dashboard; ESP-NOW → camera acks; OLED updates on serial). The full OCR leg was verified by code trace and prior sessions; a fresh photo-to-verdict run on the bench is the remaining confirmation.
6. **Is LPR real or mocked?** **Real** (Google Cloud Vision; no mock or hardcoded plate anywhere; failures fall to human review, never auto-approve).
7. **Is authorization enforced securely?** For **human users, yes** (server-side JWT + role checks on every endpoint and SSE event). For **devices, no** (unauthenticated, MAC-spoofable) — and the two image endpoints are unauthenticated.
8. **Does offline handling prevent incorrect availability?** In the shipped UI, yes (offline spots are visibly untrusted and excluded from recommendations); at the API level, no (staleness is a client convention, not a backend guarantee).
9. **Can the project be demonstrated now?** **Yes** — locally today, and in the cloud after the documented deploy steps; apply P0 fixes to de-risk OCR noise and accidental data wipes.
10. **Five most important next actions:**
   1. Validate OCR output as a 7–8-digit Israeli plate before lookup (P0-1).
   2. Guard the seeder against wiping configured spots (P0-2).
   3. Decide incentive points: implement minimal version or formally descope in docs (P1-3).
   4. Move offline/low-battery detection server-side with rate-limited admin alerts (P1-4).
   5. Add state-machine tests for `main.py`'s heartbeat/park/review flows and delete the broken SQLite test (P1-6/8).
