# ParkMe — User Story Implementation Audit

**Fresh code-first audit against `Documentation/USER_STORIES.md`.**
No statuses, scores, or line numbers were copied from the previous `PROJECT_AUDIT_REPORT.md`; every claim below was re-verified against the current working tree.

---

## 1. Executive Summary

ParkMe is a **deployed, working system**: the backend runs on Google Cloud Run (me-west1), the frontend on Firebase Hosting, and the LPR pipeline was validated against **31 real plate images with a 90.3% exact-match rate**. Two previously reported blockers are now **genuinely fixed and verified in current code**: (1) calibration now truly derives the occupancy threshold from the measured baseline and that threshold is what classification uses — confirmed end-to-end in firmware and reported working on real hardware; (2) OCR output is now validated as a plausible 7–8-digit Israeli plate with 12 passing unit tests plus the 31-image pipeline run.

Of 13 requirements: **2 DONE (US-06, US-11), 10 PARTIAL, 1 MISSING (R-02 incentive points)**. The recurring themes across the PARTIAL stories are: alerting exists only inside an open admin dashboard (staleness/offline is computed solely by the browser); there is no low-battery threshold or alert; sensor-node configuration still requires the Firestore console or a seed script that **unconditionally wipes all spots**; hardware endpoints and evidence-image endpoints are unauthenticated; and the backend's 1,600-line state machine has no integration tests. The 31-image LPR run also proved that **misreads can still pass the 7–8-digit gate** (2 of 31 images produced a wrong-but-valid-looking plate), so false violations against legitimate drivers remain possible.

Readiness: **Prototype — Ready. Demo — Ready** (system is live and evidenced). **Pilot — Limited** (device auth, server-side alerting, config UI, integration tests needed). **Production — Not Ready.**

## 2. Branch, Commit, Date, Commands

| Item | Value |
|---|---|
| Branch | `main` |
| Commit | `f710e0d3ed1a2b2fad6b90f5e9e22e5ce122b34c` (merge of PR #8 `amer_pics_tests`) |
| Working tree | Clean except uncommitted doc edits (`cloud_setup_complete_guide.md`) and the two new audit input docs |
| Audit date | 2026-07-11 |

Commands run (all safe/read-only; no seed scripts executed, nothing pushed):

```
git rev-parse / git log / git diff --name-status fdca085~1..f710e0d
python -m py_compile Backend/main.py Backend/parking_logic.py        → OK
python -m unittest discover -s tests -t . -v                          → ImportError (tests/ lacks __init__.py — finding M-2)
python -m unittest tests.test_plate_extraction tests.test_backend_parking_logic -v  → 16/16 OK
python -m unittest tests.test_backend_database -v                     → BROKEN (ModuleNotFoundError: _support)
grep-based symbol/line verification across Backend, Frontend, ESP32
```

The image-based LPR pipeline test (`tests/test_lpr_pipeline.py`) was **not re-executed** in this audit (it requires a running backend and posts real images, creating live Firestore logs). Its committed results log (`tests/lpr_test_results.log`, run 2026-07-10 against a local server with live Vision credentials) was inspected and is treated as recent runtime evidence.

## 3. Architecture and Repository Inventory

| Component | Location | Verified state |
|---|---|---|
| Sensor firmware | `ESP32/ParkMeSensorNode/ParkMeSensorNode.ino` (~1,650 lines) | Dual-core FreeRTOS: Core 0 `networkTask` (:1436) handles WiFi/SSE/telemetry; Core 1 `loop()` senses + renders OLED. HTTPS via `WiFiClientSecure` (`setInsecure()` at :782, :1119, :1321) |
| Camera firmware | `ESP32/ParkMeCameraNode/ParkMeCameraNode.ino` (~600 lines) | ESP-NOW-triggered capture; upload retries ×3 (:392); failure now unlatches the per-cycle capture flag (:549) for automatic retry |
| Shared firmware lib | `ESP32/ParkMeCommon/ParkMeCommon.h` | Pure decision helpers: `computeOccupiedThreshold` (:71), `classifyDistanceCm` (:89), `batteryPercentFromVoltage` (:106) — all compile-time tested |
| Backend | `Backend/main.py` (1,630 lines), `Backend/parking_logic.py` | FastAPI; endpoints mapped in §detailed reviews; real Google Vision OCR (`extract_license_plate`, main.py:456) |
| Plate validation | `Backend/parking_logic.py:8–49` (`extract_plate_from_ocr_text`) | Two-pass 7–8-digit extraction; wrapped by `_extract_plate_digits` (main.py:431) |
| Firestore | Collections: `users`, `vehicles`, `parking_spots`, `parking_logs`, `spot_captures` | Seeded by `Backend/seed_firestore.py` (wipes `parking_spots` — :48) |
| Auth | Firebase Auth + Firestore roles; JWT verified server-side (main.py:1031) | Admin gate `get_current_admin` (main.py:1271) |
| Frontend | `Frontend/` (app.js 815 lines, index.html, style.css) | Deployed to Firebase Hosting; `API_BASE` points to the Cloud Run backend when served from `.web.app` (app.js:6–11) |
| Tests | `tests/` (3 live modules + 1 broken + 31-image suite), `ESP32/ParkMeFirmwareCompileTests/`, `Unit Tests/` (3 HW sketches + report) | 16 unit tests pass; image suite 28/31; `test_backend_database.py` broken |
| Deployment | `Backend/Dockerfile`, `Backend/cloudbuild.yaml`, `Backend/.dockerignore`, `firebase.json` | All verified (§8) |
| Ops docs | `Documentation/step_by_step_deployment.md`, `cloud_setup_complete_guide.md` (live URLs, teardown), `PROJECT_OVERVIEW.md` | Current |

## 4. Requirement Traceability Matrix

| ID | Requirement | Status | Code evidence | Test/runtime evidence | Main gap | Risk | Priority | Effort |
|----|-------------|--------|---------------|------------------------|----------|------|----------|--------|
| US-01 | Real-time availability | PARTIAL | Sensor sampling/classify `ParkMeSensorNode.ino:1641`, heartbeat `main.py:516`, SSE `main.py:1231`, frontend refresh `app.js` SSE+5s poll | Live deployment; 4 ordering unit tests; no state-transition tests | Staleness computed only in browser (`app.js:12,140`); no backend `unknown` state | Medium | P1 | M |
| US-02 | LPR access | PARTIAL | Capture `ParkMeCameraNode.ino:522–556`, Vision `main.py:456`, validation `parking_logic.py:20`, authz `main.py` park flow, review flow | **12/12 plate unit tests; image pipeline 28 PASS / 3 FAIL / 0 ERROR (90.3%)** | 2/31 misreads passed the 7–8-digit gate as wrong plates → possible false violations | Medium | P1 | S |
| US-03 | Violation alert | PARTIAL | Violation decision + evidence in park flow; SSE admin-only `log_event`s; accept/reject `main.py:1362,1422` | Verified live earlier; anomaly log persists (`main.py:1147`) | Alert only in open dashboard; no ack/resolved lifecycle beyond sentinel states | Medium | P1 | M |
| US-04 | Accessible parking | PARTIAL | Category `special-needs-driver` seeded; server-side filter + authz; recommendation `app.js:220–238` with empty-state (:231) | Deployed & working; no automated authz tests | No role×category test matrix; single-role model undocumented | Low | P2 | S |
| US-05 | Battery & maintenance | PARTIAL | Voltage→% `ParkMeCommon.h:106` (bounded, compile-tested), heartbeat payload validated 0–100, admin card shows battery | Compile-time asserts | **No low-battery threshold or alert anywhere** (grep: zero matches) | Medium | P1 | S |
| US-06 | Device access display | DONE | OLED state machine + server-command priority; SSE display stream `main.py:1203` + poll fallback (:729) + result ack (:747); zero-latency SSE (commit d0253e1) | HW OLED sketch; verified live on hardware (WELCOME/DENIED observed in earlier session) | Long-run field burn-in only | Low | P2 | S |
| US-07 | Logs & statistics | PARTIAL | Entry/exit lifecycle; `/logs` admin-only, DESC, limit 50 (`main.py:1155–1160`); usage-stats (`main.py:1277`) | Working in deployed system | No date filters; usage-stats scans the **entire** `parking_logs` collection (:1280); retention undocumented | Medium | P1 | M |
| US-08 | Node configuration | PARTIAL | Config lives in Firestore `parking_spots` and drives authz/visibility | Live system configured this way | **No admin endpoint/UI** — console edits or `seed_firestore.py` which wipes spots (:48); no category validation; duplicate MACs unchecked | High | P0 (wipe guard) / P1 (endpoint) | S / M |
| US-09 | Offline handling | PARTIAL | WiFi flag + SSE backoff `networkTask` (:1444–1476); NVS single-slot telemetry (:955–978); camera retry unlatch (:549); frontend offline badges+toasts (`app.js:195–218`) | Race-ordering tests (4) pass; WiFi-loss behavior seen on bench | Backend computes no staleness (AC2); offline alert requires open dashboard (AC4); one unsent state, no timestamps; `/telemetry/bulk` (main.py:1490) has **0 firmware callers** | High | P1 | M |
| US-10 | Web GUI | PARTIAL | Login/roles/live grid/admin panel; deployed at Firebase Hosting; SSE reconnect + listener cleanup | Live use | 1 `@media` query in style.css; several `innerHTML` sinks (`app.js:85,186,666,696,704`); some fetch errors console-only; no frontend tests/checklist | Medium | P2 | M |
| US-11 | Calibration/setup | DONE | Button (:948,1228 — 4s hold, no reflash), 15 samples w/ invalid rejection (:1004–1018), NVS persist (:1001), **threshold = baseline − 30cm delta, floored 8cm (:984–987, :997–1000)**, safe default fallback (:991–992), used by `classifyDistanceCm` (:1641), OLED PASS/FAIL (:1027,1039) | Compile-time asserts on `computeOccupiedThreshold`; technician-tested on real hardware (reported working this week) | No upper-bound sanity on absurdly large baselines beyond measurement cap (`kSensorMeasurementCapCm`, :113) | Low | P2 | S |
| R-01 | Spot recommendation | PARTIAL | `renderRecommendation` `app.js:220–238`: role-filtered input (server), excludes occupied+offline, deterministic first-by-id, empty-state message (:231) | Live behavior | Frontend-only; selection rule not documented; no tests | Low | P2 | S |
| R-02 | Incentive points | MISSING | Zero matches for points logic/storage/UI in Backend, Frontend, seeds | — | Entire feature absent | High (stated requirement) | P1 | M |

## 5. Detailed User-Story Reviews

### US-01 — Real-time availability — PARTIAL
**Flow:** HC-SR04 sampled every 500 ms, 3-sample average with invalid readings excluded (`sampleAverageDistance`, sensor :1004–1018) → `classifyDistanceCm(distance, occupiedThresholdCm, freeLimit)` (:1641) distinguishing FREE/OCCUPIED/UNKNOWN → heartbeat POST with MAC + battery (validated by Pydantic) → `receive_heartbeat_data` (main.py:516) writes `is_occupied`, `last_seen`, broadcasts SSE `spot_update` → dashboard updates without refresh (SSE + 5 s polling safety net); role-filtered spot visibility server-side (`/spots`, main.py:1067). Stable IDs = Firestore doc ids; multiple nodes = MAC→spot mapping.
**Unmet criteria:** (8, partially) an offline sensor is flagged only because the *browser* compares `last_seen` against `SPOT_STALE_MS` (app.js:12, :140–148) — any other API consumer sees stale `is_occupied` as fresh; (10) reconnection handled (SSE `onerror` + poll), but no automated tests for transitions/staleness.
**Impact/risk:** Medium — correct in shipped UI, unguaranteed at API level.
**Recommendation:** compute `status: unknown` server-side from `last_seen` in `/spots` and SSE payloads; add transition unit tests. **P1 / M**

### US-02 — LPR access — PARTIAL
**Flow verified end-to-end in current code:** ESP-NOW trigger → `handlePendingEspNowCapture` (camera :522) sets in-progress, `performGateScan` captures fresh frame (FIFO flush via dummy grabs) and uploads multipart with camera MAC, 3 attempts (:392–395); TLS to Cloud Run (`setInsecure`, :390) → `/api/v1/sensors/park` (main.py:756) → Vision `text_detection` + `document_text_detection` fallback (:456) → `extract_plate_from_ocr_text` (parking_logic.py:20): pass 1 contiguous digit tokens with dash-like separators, pass 2 per-line digit join, accept only 7–8 digits → vehicle doc-id lookup → user → role vs. spot category (admin bypass) → WELCOME/DENIED + log + SSE + display command. Unreadable → `UNIDENTIFIED` review flow (fails closed). Duplicate sessions prevented by active-log sentinel checks + `should_preserve_recent_active_log` (unit-tested). A dedup TTL cache exists but is write-only (`LPR_DEDUP_CACHE`, main.py:170/:910 — dead code).
**Test evidence (exact):** `tests/test_plate_extraction.py` **12/12 pass** (clean, dashed, noisy multi-line, cross-line concatenation trap, phone number, short fragment, empty). Image pipeline (`tests/lpr_test_results.log`, 31 images): **28 PASS, 3 FAIL, 0 ERROR — 90.3%**. Failures: `4528139.jpg` → no plate → `manual_review` (**safe** failure); `7023709.jpg` → extracted `07378510`; `9656026.jpg` → extracted `19656026` (**unsafe**: wrong 8-digit strings passed validation → would be treated as unregistered → false violation).
**Unmet criteria:** (5/9 partially) misreads can still fabricate plausible plates. Note both bad reads are 8-digit strings beginning with `0`/spurious prefix — Israeli 8-digit plates never begin with 0, so a leading-zero rejection alone fixes 1 of 2.
**Recommendation:** reject plates with leading `0`; when the two Vision modes disagree, prefer agreement or fall to review; log OCR confidence. **P1 / S**

### US-03 — Violation alert — PARTIAL
**Flow:** unregistered plate or role mismatch → `is_violation=true` log with spot, timestamp, plate/sentinel, evidence image base64; SSE `log_event` delivered **only to admin connections**; frontend toast + security log with "Show Picture" (app.js:696–708); accept/reject endpoints (main.py:1362/1422) admin-gated, reject permanently attaches evidence. Duplicates limited by one-active-log-per-spot. Missed alerts are recoverable via `/logs` (last 50 anomalies), so not silently lost — but only if the admin later opens the dashboard.
**Unmet:** (4/5 partially) no out-of-band channel (email/push); (7) no unresolved/acknowledged lifecycle beyond sentinel plates; (8) SSE delivery failures only surface as disconnects.
**Recommendation:** minimal ack field + one out-of-band channel (Cloud Function on `parking_logs` writes). **P1 / M**

### US-04 — Accessible parking — PARTIAL
Category `special-needs-driver` is a first-class spot category; server filters both `/spots` and SSE per role, so an accessible driver sees only accessible spots and others never see them as recommendations; backend enforces authorization at park time (not frontend-only); empty-state message exists (app.js:231). **Unmet:** no automated tests for the authz matrix; single-role model (accessible drivers have no base role) is a design decision that should be documented. **P2 / S**

### US-05 — Battery & maintenance — PARTIAL
Sensor reads divider voltage (`readBatteryVoltage`, :1045–1053), converts with bounded, compile-tested `batteryPercentFromVoltage`; heartbeat schema rejects <0/>100; Firestore stores value + `last_seen`; admin cards show 🔋 per spot; staleness covered by the 2-min offline badge. **Unmet:** (5, 6) **no low-battery threshold and no warning/alert anywhere** — grep for any low-battery symbol returns nothing; (9) no runtime tests for edge readings. The team has stated battery is demo-hardware-limited (pin unwired reads 0%), so this is a knowing gap — it should be either implemented (single threshold check + rate-limited admin log_event, small) or explicitly descoped in docs. **P1 / S**

### US-06 — Device access display — DONE
Display is bound to the spot's node; backend queues WELCOME/DENIED to the correct `display_id`; delivery is **SSE-first with zero latency** (`/api/v1/displays/stream`, main.py:1203) plus poll fallback (:729) and an explicit result-ack endpoint (:747); firmware renders on Core 1 with a priority model (server verdict > local camera status > idle) and timed holds, so a stale or local message can't mask the final decision; scanning/failure/review states all have messages. Evidence: HW OLED test sketch, live hardware verification of both WELCOME and DENIED flows, commit `45c65d4` specifically fixed heartbeat/ACK starvation while SSE is connected. Remaining: only long-run burn-in. **P2 / S**

### US-07 — Logs & statistics — PARTIAL
Entry/exit recorded across heartbeat/park lifecycle; sessions distinguishable (active = no `exit_time`; sentinels encode review states); `/logs` admin-only with limit 50 ordered DESC (main.py:1155–1160) — intentionally anomalies-only (comment :1189–1191); `/admin/usage-stats` (main.py:1277) computes occupancy, peak hour, busiest spot, durations, outcome counters; IL timezone handled centrally. **Unmet:** (6) no date-range or spot filters; usage-stats does `db.collection("parking_logs").get()` (:1280) — **unbounded full-collection scan** whose cost grows forever; (7) limit-50 only, no pagination; (9) retention/evidence-image policy undocumented. **P1 / M**

### US-08 — Node configuration — PARTIAL
Configuration (spot id, sensor/camera MACs, category) lives in `parking_spots` documents and genuinely drives authorization and visibility. **Unmet:** (1) no admin API or UI — changing a node means the Firestore console or `seed_firestore.py`; (3) no category whitelist anywhere (a typo silently breaks a spot); (4) duplicate MACs resolve arbitrarily via `.limit(1)` (main.py:365); (8/10) no validation errors, no tests. **Operational hazard:** `seed_parking_spots` **unconditionally wipes the collection** (seed_firestore.py:48) — this has already destroyed hand-entered real MACs once during development. **P0 (guard the wipe, S) + P1 (admin endpoint with enum + MAC-uniqueness, M)**

### US-09 — Offline & failure handling — PARTIAL
**Verified resilience:** heartbeats carry `last_seen`; `networkTask` marks WiFi state, retries SSE with exponential backoff 3→30 s (:1462–1472), falls back to display polling; one unsent state persists in NVS and is flushed on reconnect (:955–978); **camera now un-latches after a failed upload and retries on the next sensor re-broadcast** (:546–554 — fixed since the previous audit); frontend shows OFFLINE badges, one toast per offline/recovery transition, and excludes offline spots from recommendations; out-of-order replay is guarded by `should_preserve_recent_active_log` (4 passing tests).
**Unmet:** (2) backend computes **no** stale/offline status — grep confirms no server-side staleness logic; (4) admin "notification" exists only while a dashboard is open; (7 partially) a single unsent state with no timestamp — history during an outage is lost; `/telemetry/bulk` (main.py:1490) has **zero firmware callers** (grep across `ESP32/` = 0 matches) — dead capacity; (10) no timeout/reconnect/replay integration tests. **P1 / M**

### US-10 — Web GUI — PARTIAL
Login (Firebase, auto-login persistence, sign-out cleanup), server-verified role, live dashboard for both roles, near-real-time updates (SSE + poll), deployed and reachable at the Firebase Hosting URL with `API_BASE` correctly wired to Cloud Run (app.js:6–11). Listener hygiene on reconnect exists (`offlineSpotIds.clear()`, SSE close/reopen).
**Unmet:** (5) several fetch failures log to console without a visible banner; (6) `style.css` contains exactly **1** `@media` query — thin for "on the go"; (8) `innerHTML` used for toasts, stats, spot cards, and log rows (app.js:85, 186, 666, 696, 704) — currently low exposure (plates are digit-validated) but an XSS-prone pattern; (10) no frontend tests or written manual checklist. **P2 / M**

### US-11 — Calibration / setup mode — DONE
Full trace against current code:
1. **Button:** `calibrationButtonPressed` (:948) on the configured GPIO with internal pull-up; runtime entry via 4-second hold (`handleCalibrationButton`, :1228–1242) — **no reflash needed**; boot-time entry also present (:1601).
2. **Sampling:** 15 samples, 120 ms apart; invalid (≤0 or above `kSensorMeasurementCapCm`, :113) readings are excluded; all-invalid → −1 (:1004–1018).
3. **Failure feedback:** no echo → serial + OLED "Calibrate FAIL / No echo", previous baseline kept (:1025–1031).
4. **Persistence:** `preferences.putFloat("base_cm", …)` (:1001) — per-node NVS, survives reboot.
5. **Threshold calculation:** `occupiedThresholdCm = computeOccupiedThreshold(baseline, PARKME_SENSOR_OCCUPIED_DELTA_CM, PARKME_SENSOR_MIN_THRESHOLD_CM)` — i.e. baseline − 30 cm, floored at 8 cm — in **both** `saveCalibration` (:997–1000) and `loadCalibration` after reboot (:984–987).
6. **Safe fallback:** no stored baseline → default baseline + default threshold constants (:991–992).
7. **Classification call:** `loop()` classifies with `occupiedThresholdCm` (:1641).
**Changing calibration therefore genuinely changes occupied/free detection.** The old audit's "threshold is always fixed at 20 cm" claim is **no longer true** and is explicitly retired. Success feedback shows the computed trigger on OLED + serial (:1034–1040). Recalibration overwrites safely. Evidence: compile-time asserts on the threshold math (`ParkMeFirmwareCompileTests`), and the technician flow was exercised on real hardware this week (reported working). Residual nit: no explicit upper-bound rejection for implausible baselines beyond the sampling cap. **P2 / S**

### R-01 — Spot recommendation — PARTIAL
`renderRecommendation` (app.js:220–238) filters the already-server-role-filtered spot list to non-occupied, non-offline spots, sorts by id, recommends the first, and shows an explicit empty-state (:231). Deterministic and cannot bypass backend authorization (input is server-filtered). **Unmet:** rule not documented; no tests; frontend-only. **P2 / S**

### R-02 — Incentive points — MISSING
Exhaustive grep across `Backend/`, `Frontend/`, and seeds finds no points field, award logic, transaction record, or UI. Every acceptance criterion is unmet. Either implement minimally (per-user counter awarded transactionally on authorized session close, visible in `/users/me` + header badge) or formally descope in the project docs before grading. **P1 / M**

## 6. Cross-cutting Findings (hypothesis verdicts)

| # | Hypothesis | Verdict | Evidence |
|---|---|---|---|
| 1 | Incentive points absent | **CONFIRMED** | Zero matches repo-wide |
| 2 | Config requires Firestore edits/seed scripts | **CONFIRMED** | No admin config endpoint in main.py route table; seeder wipes spots (seed_firestore.py:48) |
| 3 | Low-battery alerts absent | **CONFIRMED** | No threshold/alert symbol in backend or frontend; display-only (app.js battery line) |
| 4 | Violation/offline alerts only with dashboard open | **CONFIRMED** | Alerts = SSE to connected admin browsers + in-page toasts; no other channel |
| 5 | Sensor keeps only one unsent telemetry state | **CONFIRMED** | Single `pendingTelemetry` struct in NVS (:955–978), no timestamp, overwritten on each queue |
| 6 | Stale/offline computed only by frontend | **CONFIRMED** | `SPOT_STALE_MS`/`isSpotOffline` in app.js (:12/:140); no backend staleness code |
| 7 | Logs/stats lack date filters, pagination, bounded queries, retention | **CONFIRMED** | `/logs` fixed limit 50, no params (:1147–1160); usage-stats full scans (:1279–1280); no retention docs |
| 8 | Mobile & API-error UI incomplete | **CONFIRMED** | 1 `@media` query; several console-only error paths |
| 9 | Backend integration coverage weak | **CONFIRMED** | No tests import `main.py`; 16 unit tests cover only pure helpers |
| 10 | Legacy SQLite test stale | **CONFIRMED (BROKEN)** | `test_backend_database.py` → `ModuleNotFoundError: _support`; targets the removed SQLite schema |
| 11 | Hardware endpoints trust MACs without auth | **CONFIRMED** | `/sensors/*`, `/displays/*`, `/telemetry/bulk` have no auth dependency; evidence-image endpoints `/captures/{spot_id}` (:217) and `/logs/{id}/capture` (:238) are also **unauthenticated** — violation photos retrievable by id |
| 12 | CORS and TLS permissive | **CONFIRMED** | `allow_origins=["*"]` (main.py:89); both boards call `setInsecure()` (sensor :782/:1119/:1321, camera :299/:390) — HTTPS without certificate validation |
| 13 | In-memory SSE/display state vs. Cloud Run scaling | **CONFIRMED but mitigated** | State is in-process; `cloudbuild.yaml` pins `--max-instances=1 --min-instances=1 --timeout=3600` with explanatory comments — consistent by construction, horizontal scaling impossible |

Additional maintainability findings: **M-1** `LPR_DEDUP_CACHE` is write-only dead code (main.py:170, :910); **M-2** `tests/` lacks `__init__.py`, so `python -m unittest discover -s tests` fails (modules must be run by name); **M-3** `PARKME_GATE_MAX_CAPTURE_RETRIES` exists in `SECRETS.example.h` (=1) but the camera hardcodes `maxRetries = 3` (:392) — config/code contradiction; **M-4** `main.py` at 1,630 lines mixes transport, domain logic, and persistence.

## 7. Test Results (exact)

| Suite | Result |
|---|---|
| `tests.test_plate_extraction` | **12/12 pass** |
| `tests.test_backend_parking_logic` | **4/4 pass** |
| `tests.test_backend_database` | **BROKEN** — `ModuleNotFoundError: _support` (legacy SQLite era) |
| `python -m unittest discover -s tests` | **Fails to collect** (missing `__init__.py`) |
| `py_compile` main.py + parking_logic.py | OK |
| LPR image pipeline (committed log, 2026-07-10) | **31 images: 28 PASS / 3 FAIL / 0 ERROR = 90.3%**. Safe failure ×1 (`manual_review`); unsafe misreads ×2 (`07378510`, `19656026`) |
| Firmware compile-time asserts | Present and meaningful (threshold/battery/classify/parse); require Arduino IDE to execute — NOT TESTABLE here |
| Hardware sketches (`Unit Tests/`) | Documented with PASS report (`HARDWARE_UNIT_TESTS_REPORT.md`); calibration + OLED additionally verified on real hardware this week (reported) |

OCR is therefore **not 100% reliable** and must not be presented as such: the honest claim is *"90.3% exact-match on a 31-image test set; failures either fall to manual review or are rejected as violations — two misreads produced wrong plates that passed format validation."*

## 8. Deployment Findings

| Item | Finding |
|---|---|
| Cloud Run `$PORT` | ✅ `CMD uvicorn … --port ${PORT:-8000}` (Dockerfile:26) |
| Credentials | ✅ ADC — `credentials.ApplicationDefault()` path with `FIREBASE_PROJECT_ID=parkme-technion-f280b` env var set in cloudbuild; no key file in image |
| Secret exclusion | ✅ `Backend/.dockerignore` excludes `serviceAccountKey.json`, `env`, `.env`, venvs; secrets git-ignored |
| Hosting → backend URL | ✅ `app.js:9` points `.web.app` origins at `https://parkme-backend-31114651685.me-west1.run.app/api/v1`; frontend live at `https://parkme-technion-f280b.web.app` |
| CORS | ⚠️ `*` — should be locked to the Hosting origin now that both URLs are fixed (pilot blocker, not demo) |
| Scaling vs. in-memory state | ✅ consciously pinned to exactly 1 instance (max=min=1); documented in cloudbuild comments. Restart drops SSE clients (they reconnect) |
| Timeouts | ✅ `--timeout=3600` for long-lived SSE |
| Vision/Firestore config | ✅ same ADC identity; region me-west1 |
| Logging/health | ⚠️ Plain `logging` INFO to stdout (Cloud Logging picks it up); no `/healthz`, no error metrics/alerting |
| Rollback/repeatability | ✅ `cloudbuild.yaml` is a repeatable pipeline; Cloud Run keeps revision history (traffic rollback available); step-by-step + post-deploy ops docs exist. No explicitly written rollback runbook |
| Unauthenticated ingress | ⚠️ `--allow-unauthenticated` + MAC-trust hardware endpoints + public evidence-image endpoints = anyone on the internet can post fake heartbeats/photos or fetch violation images by id — **pilot blocker**, acceptable for a course demo |

**Risk classing:** Demo blockers: none found. Pilot blockers: device/endpoint auth, CORS lockdown, server-side staleness+alerting, seeder wipe guard. Production blockers additionally: TLS cert validation on boards, retention/privacy policy, integration tests, observability/alerting, points (if in scope).

## 9. Prioritized Improvement Backlog

**T1 — Guard the seeder against wiping configured spots** · US-08 · Problem: `seed_parking_spots` deletes the whole collection unconditionally (seed_firestore.py:48); already destroyed real MACs once. Impact: one command can break the live deployment. Files: `Backend/seed_firestore.py`. Approach: require `--wipe` flag for deletion; default to merge/update per document. Acceptance: running without flags preserves existing MACs; with `--wipe` behaves as today. **P0 / S** · deps: none

**T2 — Harden plate acceptance against plausible misreads** · US-02 · Problem: 2/31 test images yielded wrong 8-digit plates passing validation (`07378510`, `19656026`). Impact: legitimate drivers can be logged as violations. Files: `Backend/parking_logic.py`, `tests/test_plate_extraction.py`. Approach: reject leading-zero plates (Israeli plates never start with 0 — catches one failure class); when the two Vision passes disagree on the digits, route to manual review instead of trusting the first. Acceptance: new unit tests for both failure images' raw OCR text; image-suite pass rate not reduced. **P1 / S** · deps: none

**T3 — Server-side staleness + offline/low-battery alerts** · US-01, US-05, US-09 · Problem: staleness lives only in the browser; no low-battery logic at all. Impact: no admin at the dashboard = no alert ever; API consumers read stale data as fresh. Files: `Backend/main.py`, `Frontend/app.js`. Approach: compute `status ∈ {free,occupied,unknown}` from `last_seen` in `/spots` + SSE; on heartbeat, emit rate-limited admin `log_event` for battery < threshold (env-configurable) and for spots newly stale (piggyback on existing request traffic or a lightweight periodic task). Acceptance: unit tests for status derivation; battery 15% heartbeat produces exactly one alert per cooldown window. **P1 / M** · deps: none

**T4 — Admin spot-configuration endpoint with validation** · US-08 · Problem: config requires console/seed access; category values and MAC uniqueness unvalidated. Files: `Backend/main.py` (+ optional small admin form in `app.js`). Approach: `PUT /api/v1/admin/spots/{id}` gated by `get_current_admin`; category enum whitelist; reject duplicate MACs (query before write). Acceptance: tests for valid update, bad category (422), duplicate MAC (409), non-admin (403). **P1 / M** · deps: T1 (so seeding doesn't clobber configured spots)

**T5 — Decide incentive points: minimal implementation or formal descope** · R-02 · Problem: stated requirement, zero implementation. Files: `Backend/main.py`, `seed_firestore.py`, `Frontend/app.js` — or `Documentation/` only if descoped. Approach (if implemented): `points` on users; award once on authorized session close in the heartbeat exit path using a Firestore transaction keyed by log id (idempotent); show in `/users/me` + header; admin audit via a `point_transactions` subcollection. Acceptance: duplicate exit events award once; non-admin cannot mutate points. **P1 / M** · deps: none

**T6 — Backend integration tests for the state machine** · US-01/02/03/09 · Problem: 1,630-line core has no tests; regressions (like the ones teammates fixed by hand this week) are invisible. Files: new `tests/test_main_flows.py`, small `get_firestore_db` injection refactor; add `tests/__init__.py`; delete `tests/test_backend_database.py`. Approach: fake Firestore double; cover heartbeat entry/exit, camera-first grace, bouncy driver, ghost-log review, accept/reject. Acceptance: `python -m unittest discover` collects and passes everything. **P1 / L** · deps: none

**T7 — Device & evidence endpoint authentication** · security · Problem: hardware endpoints and violation-photo endpoints are open to the internet. Files: `main.py`, both `.ino`, `ParkMeCommon.h`, SECRETS templates. Approach: shared-secret HMAC header (secret already anticipated by `env.example`) verified on `/sensors/*`, `/displays/*`, `/telemetry/*`; require admin auth on `/captures/*` and `/logs/*/capture` (dashboard already sends tokens). Acceptance: unsigned requests → 401; boards with secret work end-to-end. **P1 / L** (needs reflash) · deps: hardware access

**T8 — Bounded, filterable logs & stats** · US-07 · `?from&to&spot_id` on `/logs`; date-window cap on usage-stats instead of full scan; document retention. **P2 / M**

**T9 — Frontend robustness pass** · US-10 · Visible API-error banner; convert `innerHTML` sinks to `textContent`/element construction; 2–3 responsive breakpoints; write a manual test checklist. **P2 / M**

**T10 — Dead-code and config hygiene** · maintainability · Remove `LPR_DEDUP_CACHE`, honor or remove `PARKME_GATE_MAX_CAPTURE_RETRIES`, wire `/telemetry/bulk` to firmware (with timestamps) or delete it. **P2 / S–M**

## 10. Suggested Implementation Order

T1 → T2 → T3 → T4 → T5 → T6 → T7 → T8 → T9 → T10.
Rationale: T1 removes a live-data hazard in minutes; T2 closes the only user-facing correctness hole proven by test data; T3 delivers the single most-cited missing behavior across three stories; T4/T5 close the two requirement-level gaps a grader will look for; T6 locks everything in place before the security work (T7) touches firmware.

## 11. Documentation / Code Contradictions

1. `ESP32/SECRETS.example.h` documents `PARKME_GATE_MAX_CAPTURE_RETRIES = 1`; camera hardcodes 3 attempts (`ParkMeCameraNode.ino:392`).
2. `PROJECT_AUDIT_REPORT.md` (2026-07-10) states the occupancy threshold is fixed at 20 cm and calibration is non-functional — **no longer true**; superseded by this audit (US-11 DONE).
3. Older docs describe multi-event offline replay via `/telemetry/bulk`; firmware persists exactly one state and never calls that endpoint.
4. `tests/test_backend_database.py` implies a SQLite schema (`users.points` included) that no longer exists anywhere.
5. `seed_firestore.py`'s docstring says it "seeds test data" but does not mention it **deletes all existing parking spots** first.

## 12. Readiness Verdict

| Level | Verdict | Basis |
|---|---|---|
| Course prototype | **Ready** | All core flows implemented, integrated, and evidenced |
| Demo | **Ready** | Deployed and live (Cloud Run + Firebase Hosting); LPR 90.3% on real images; calibration and display verified on hardware. Run T1 (seed guard) before any demo-day reseeding |
| Pilot | **Limited** | Requires T3 (server-side alerting), T4 (config surface), T7 (endpoint auth), CORS lockdown, T6 (tests) |
| Production | **Not Ready** | All pilot items plus TLS validation on devices, retention/privacy policy, observability/alerting, load-tolerant statistics |

---

## Five Highest-Value Improvements (in implementation order)

1. **T1 — Seeder wipe guard** (P0/S): stop `seed_firestore.py` from silently deleting configured spots.
2. **T2 — Plate misread hardening** (P1/S): leading-zero rejection + dual-pass agreement; the 31-image suite already gives you the regression harness.
3. **T3 — Server-side staleness + offline/low-battery alerts** (P1/M): closes the biggest shared gap in US-01, US-05, and US-09.
4. **T4 — Admin spot-configuration endpoint with category/MAC validation** (P1/M): makes US-08 real without console access.
5. **T5 — Incentive points: implement minimally or formally descope** (P1/M): the only fully MISSING requirement — decide before grading.
