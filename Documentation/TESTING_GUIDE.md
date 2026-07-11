# ParkMe — Complete Testing Guide

How to test every part of the system: automated tests, hardware tests, end-to-end scenarios, and failure/recovery drills. All timings and endpoint names below are taken from the current code, not from memory — where a number matters, the source is cited.

---

## 1. Test Environment

| Item | Value |
|---|---|
| Backend (cloud) | `https://parkme-backend-31114651685.me-west1.run.app` |
| Dashboard | `https://parkme-technion-f280b.web.app` |
| Local backend (optional) | `Backend\run_local_backend.ps1` → `http://<your-PC-IP>:8000` |
| Admin login | `admin@technion.ac.il` / `password123` |
| Student login | `student@technion.ac.il` / `password123` (plate `1234567`) |
| Lecturer login | `lecturer@technion.ac.il` / `password123` (plate `9876543`) |
| Accessible driver | `jane@technion.ac.il` / `password123` (plate `1122334`) |
| Real hardware spot | `C1` (sensor MAC `A8:42:E3:46:F4:E0`, camera MAC `24:6F:28:47:F9:E8`) |

### Key system timings (needed to interpret every test)

| Constant | Value | Where |
|---|---|---|
| Sensor sampling | every 500 ms, 3-sample average | firmware |
| Heartbeat interval | **20 s** (plus immediately on state change) | `SECRETS.h` |
| Dashboard OFFLINE threshold | **120 s** without heartbeat | `app.js:12` (`SPOT_STALE_MS`) |
| Occupied threshold | **calibrated**: measured target distance + 2 cm margin, clamped 3–50 cm; default 20 cm if never calibrated | sensor firmware |
| ESP-NOW occupied re-broadcast | every 2 s | `SECRETS.h` |
| Camera-first heartbeat grace | 10 s | `main.py` |
| Missing-photo review deadline | **30 s** after occupied heartbeat | `main.py` (`CAMERA_UPLOAD_GRACE_SECONDS`) |
| Bouncy-driver abort window | 90 s | `main.py` |
| Display SSE reconnect backoff | 3 s doubling to max 30 s | sensor firmware |
| Camera Wi-Fi retry | every 5 s | camera firmware |

> ⚠️ **Before ANY test session: never run `Backend/seed_firestore.py` casually.** It deletes and recreates all parking spots, replacing C1's real hardware MACs with placeholders — the boards will silently stop being recognized (this has happened twice). If someone reseeded, restore C1's MACs first (see §9).

---

## 2. Automated Tests (no hardware needed)

### 2.1 Unit tests — run these first, they take 1 second

```powershell
cd C:\Users\georg\source\repos\IOT_ParkMe
python -m unittest tests.test_plate_extraction tests.test_backend_parking_logic -v
```

**Expected: 16/16 pass.** Covers plate extraction (clean/dashed/noisy/phone-number/cross-line traps) and the heartbeat-vs-camera race-ordering logic.

Known state: `tests/test_backend_database.py` is a broken legacy file (old SQLite schema) — ignore it or delete it. Plain `unittest discover` fails because `tests/` has no `__init__.py`; run modules by name as shown.

### 2.2 LPR image pipeline (needs a running backend with Vision credentials)

Sends 31 real plate photos through the actual `/api/v1/sensors/park` endpoint and compares OCR output to the plate encoded in each filename:

```powershell
# against a local backend
python tests/test_lpr_pipeline.py
# or against the cloud
python tests/test_lpr_pipeline.py --server-url https://parkme-backend-31114651685.me-west1.run.app
```

**Expected: ~28/31 PASS (90.3% on record).** Known failures: one image falls to manual review (safe), two misread into wrong-but-valid-looking plates. A PASS rate meaningfully below 28 means a regression.
⚠️ This writes real logs to live Firestore (uses seeded spot A1's fake MACs, not C1) — fine for a dev database, don't run it during a demo.

### 2.3 Firmware compile-time tests

Open `ESP32/ParkMeFirmwareCompileTests/` in Arduino IDE and press **Verify**. If it compiles, all `static_assert` tests pass (threshold math, battery conversion, state classification, MAC parsing). A logic regression = compile error.

---

## 3. Basic Hardware Bring-up

Use the three sketches in `Unit Tests/` when hardware misbehaves — each prints PASS/FAIL to serial:
- `HW_Ultrasonic_Distance_Test` — live distance readings (also how you pick/verify the occupied threshold).
- `HW_OLED_SSD1306_I2C_Test` — I2C scan + screen render.
- `HW_ESP32CAM_Capture_Test` — camera capture sanity.

**Digit check (after the font fix):** on the sensor OLED, make sure readings containing **2, 5, 6, 7, 9** render right-side-up. A flipped 6 reads as 9 — if you see that, the board is running old firmware; re-flash.

---

## 4. Core End-to-End Scenarios

### E2E-1: Heartbeat & live availability
1. Power the sensor node; open serial monitor (115200).
2. Expect: WiFi connect → heartbeats returning **202** every ~20 s (first cloud request may take 1–2 s extra — TLS handshake).
3. Open the dashboard as admin: C1 shows FREE with battery %, and `last_seen` stays fresh.

### E2E-2: Full parking flow — authorized (WELCOME)
1. C1 online and FREE; camera node online.
2. Place a printed photo of a **registered** plate (e.g. `1234567` from `tests/test_pics/`) in front of the camera, then trigger the sensor (object within the calibrated threshold).
3. Expected chain, in order:
   - Sensor OLED: occupied detected; ESP-NOW trigger logged on serial.
   - Camera serial: capture → upload → server response.
   - OLED: **WELCOME JOHN DOE** (5 s hold).
   - Dashboard: C1 flips to OCCUPIED with the plate shown (admin view) — within ~1–2 s (SSE).
4. Remove the object → within one heartbeat C1 returns to FREE and the log gets an exit time.

### E2E-3: Unauthorized car (DENIED + violation alert)
1. Same as E2E-2 but use a **registered plate in the wrong zone** (lecturer plate `9876543` on student spot C1) or an **unregistered** valid-format plate.
2. Expected: OLED shows **ACCESS DENIED**; dashboard (admin) gets a red violation entry in the Security Log **with a "Show Picture" button** — verify the evidence photo opens.

### E2E-4: Unreadable plate → manual review (ghost log)
1. Trigger the sensor with **no plate visible** to the camera (blank paper).
2. Expected: OCR finds no valid 7–8-digit plate → Security Log shows **"Manual review is active at Spot C1"**; OLED shows the review message.
3. As admin, click **Accept** → log resolves, OLED shows welcome. Repeat and click **Reject** → violation recorded with the photo attached permanently.
4. Variant: cover the camera lens entirely / power it off, trigger the sensor → after **~30 s** the missing-photo review appears (deadline from `CAMERA_UPLOAD_GRACE_SECONDS`).

### E2E-5: Bouncy driver (short-stay abort)
1. Trigger occupancy, let the WELCOME/DENIED complete.
2. Remove the object **within 90 seconds** of arrival.
3. Expected: the session is converted to **ABORTED** ("Driver aborted parking at Spot C1" in the log) instead of a normal completed session — dashboard updates live.

### E2E-6: Calibration (technician flow)
1. Place an object at the **exact distance where a car should be detected** (anywhere from 3 to 50 cm), then hold the calibration button (GPIO13 → GND, or BOOT if configured) for **4 seconds** while running.
2. Expected: OLED "CALIBRATING / MEASURING TARGET" → **"CALIBRATE PASS / TRIGGER \<N\>CM"** where N = measured distance + 2 cm; serial prints both values.
3. **Prove it changed detection:** calibrate at 40 cm, confirm an object at 35 cm reads OCCUPIED and at 45 cm reads FREE; recalibrate at 15 cm and confirm 35 cm now reads FREE.
4. **Prove persistence:** power-cycle the board → serial prints the same trigger on boot (loaded from flash).
5. Failure feedback: calibrate with nothing in front (target beyond 50 cm or no echo) → **"CALIBRATE FAIL / TARGET TOO FAR"** (or "NO ECHO"), previous trigger kept.

### E2E-7: Role-based visibility & recommendation
1. Log in as **student**: only student-category spots visible; no license plates shown; no admin panel; recommendation banner suggests a free student spot (or the explicit "no verified free spots" message when none).
2. Log in as **jane (accessible driver)**: only the accessible spot (B1) visible.
3. Log in as **admin**: all spots, plates, battery values, Security Log, stats.
4. Verify it's server-enforced, not just hidden UI: as a student, the `/api/v1/logs` request must return **403** (check the browser dev-tools Network tab).

---

## 5. Failure & Recovery Drills (corrected timings)

### F-1: Sensor loses Wi-Fi, then recovers
1. C1 online and FREE. Kill the hotspot/router.
2. **During the outage:** OLED and detection keep working (Core 1 is network-independent). Dashboard shows **no change for up to 120 s** — that's by design (`SPOT_STALE_MS`), not 45 s.
3. **After 120 s:** the C1 card turns **OFFLINE** and the admin gets one toast. Note this only happens while a dashboard is open — offline detection is computed in the browser (documented limitation).
4. Restore Wi-Fi → the SDK auto-reconnects within a few seconds; next heartbeat (≤ 20 s) lands → card returns to FREE + "back online" toast.

### F-2: Car parks while sensor is offline (NVS queue)
1. Kill Wi-Fi. Place an object in front of the sensor (within the calibrated threshold — check YOUR threshold from the last CALIBRATE PASS screen; it is not a fixed 50 cm).
2. The state change is persisted to **flash** (it survives even a power cut — for a stronger test, cut the board's power too and repower it before restoring Wi-Fi).
3. Restore Wi-Fi → within a couple of seconds the queued state is flushed (`processPendingTelemetryAndAcks`) → dashboard flips C1 to OCCUPIED.

### F-3: Car parks AND leaves while offline
1. Kill Wi-Fi → object in for 10 s → object out → restore Wi-Fi.
2. Expected: only the **latest** state (FREE) is flushed — the backend is not stuck occupied. The intermediate OCCUPIED event is **lost by design** (single-slot queue; known limitation, documented in the audit).

### F-4: Camera offline during a capture
1. Keep the sensor online; kill Wi-Fi **only for the camera** (or unplug it).
2. Trigger occupancy. Expected sequence:
   - Sensor posts OCCUPIED normally; camera capture fails → OLED/camera serial shows "Capture failed / Retry next ping"; the cycle **un-latches** instead of deadlocking.
   - Dashboard: C1 occupied in "scanning" state; if no photo arrives within **30 s**, the Security Log shows a manual-review entry.
   - The camera still **takes the photo at the moment the car arrives** even with Wi-Fi down (serial: "Photo saved; will send after reconnect") and holds it in memory.
   - Restore camera Wi-Fi (retries every 5 s): the sensor's 2-second OCCUPIED re-broadcast makes the camera retry — and it uploads the **original photo taken at arrival**, not a new capture (serial: "Reusing photo captured earlier this cycle"). If the car leaves before Wi-Fi returns, the stale photo is discarded instead of sent (serial: "Pending photo discarded: spot_freed"). (Correct endpoint: `POST /api/v1/sensors/park` — there is no `/api/v1/camera/upload`.)

### F-5: Dashboard network loss (browser side)
1. With the dashboard open, disconnect the laptop's network for ~20 s, then restore.
2. Expected: connection dot goes red; on recovery SSE auto-reconnects (~3 s) and the 5-second polling safety net refreshes the grid — no duplicate log lines, no frozen cards.

### F-6: Backend restart (cloud resilience)
1. In Cloud Run console, deploy a new revision or restart the service (or just wait for a natural restart).
2. Expected: dashboard SSE drops and reconnects automatically; boards reconnect their display stream (backoff ≤ 30 s); no data loss (state is in Firestore, not process memory). Undelivered SSE events during the restart are lost — records still appear via the 5 s poll/logs.

---

## 6. Additional Tests Worth Running (gaps the standard scenarios miss)

1. **False-plate hardening check:** show the camera a page with a phone number (e.g. "054-1234567" — 10 digits) or a permit sticker plus a small plate fragment. Expected: **no** phantom plate; manual review instead. This guards the exact bug class fixed in `extract_plate_from_ocr_text`.
2. **6↔9 confusion (OCR + display):** test with plates containing 6s and 9s (`9656026.jpg` is a known-tricky image — it misread on record). Confirm what the *dashboard log* shows matches the physical plate, and the OLED renders the digits upright.
3. **Duplicate upload protection:** trigger the same occupancy twice quickly (camera sends the same frame up to 3×). Expected: **one** active session, one log entry — no duplicate violations or WELCOMEs.
4. **Wrong-zone admin:** park the "admin's car" anywhere — admins are authorized in every category; confirm no violation is logged.
5. **Category typo hazard (negative test, Firestore console):** temporarily set C1's `category` to `studnet` → every driver is now denied and non-admins can't see the spot; nothing warns you. Restore it after. (This is why the audit recommends a validated admin config endpoint.)
6. **Two dashboards at once:** open admin on PC + phone simultaneously; both must receive live updates; offline toasts appear on each independently.
7. **Battery field:** with the battery pin unwired it reports 0% — confirm the value displays but understand it isn't meaningful on the bench; there is **no low-battery alert** in the system (documented gap, don't test for one).
8. **Usage stats sanity:** after a test session, open the admin stats — session counts, peak hour, busiest spot should reflect what you just did (all times in IL timezone).
9. **Evidence privacy awareness (do NOT demo):** capture-image endpoints are unauthenticated by design gap — anyone with a log id can fetch violation photos. Known audit finding, pilot blocker, not a test to showcase.
10. **Cloud latency budget:** on the first request after idle periods, TLS + routing adds ~1–2 s. If heartbeats intermittently time out on serial, raise `PARKME_SENSOR_HTTP_TIMEOUT_MS` (already 5000 ms for cloud).

---

## 7. Multi-Spot Simulation (one command = a whole parking lot)

We own one physical sensor+camera (C1). `Backend/simulate_spots.py` impersonates the other five seeded spots through the **same endpoints the real boards use** — real heartbeats, real photo uploads from `tests/test_pics/`, real OCR, real authorization — so the dashboard shows a live, busy lot.

```powershell
# against the live cloud backend (default) — open the dashboard and watch
python Backend/simulate_spots.py

# quick demo pacing / only some spots / no Vision API usage
python Backend/simulate_spots.py --fast
python Backend/simulate_spots.py --spots A1,B1
python Backend/simulate_spots.py --no-photos     # note: occupied spots then hit the 30s manual-review deadline (that's correct system behavior)

# demonstrate OFFLINE detection: A2 goes silent for 3 minutes mid-run
python Backend/simulate_spots.py --offline-demo A2
```

What you'll see: cars randomly arrive (spot flips OCCUPIED + a photo appears with a WELCOME/DENIED/manual-review outcome depending on which test plate was chosen), stay 2–5 minutes, and leave (session closes with an exit time; stays under 90s log ABORTED — correct). Battery values drain slowly. `Ctrl+C` cleans up by sending a final FREE heartbeat for every simulated spot. It never touches C1 unless you explicitly include it, and never seeds or deletes anything.

## 8. Demo-Day Smoke Checklist (5 minutes, run in order)

1. `python -m unittest tests.test_plate_extraction tests.test_backend_parking_logic` → 16 OK.
2. `curl https://parkme-backend-31114651685.me-west1.run.app/docs` → 200.
3. Dashboard loads; admin login works; C1 FREE with fresh `last_seen`.
4. Object in front of sensor → OCCUPIED on dashboard within ~2 s.
5. Registered plate photo → WELCOME on OLED + plate on dashboard.
6. Blank paper → manual review appears; Accept resolves it.
7. Remove object → spot FREE, session closed (ABORTED if under 90 s — that's correct behavior, be ready to explain it).

## 9. If C1 Suddenly Shows OFFLINE and Nothing Works

90% chance someone re-ran the seeder and wiped the real MACs. Fix (from `Backend/`):

```powershell
./.venv/Scripts/python.exe -c "
from pathlib import Path; from dotenv import load_dotenv
[load_dotenv(p) for n in ('.env','env') for p in [Path(n)] if p.exists()]
import firebase_admin; from firebase_admin import credentials, firestore
firebase_admin.initialize_app(credentials.ApplicationDefault())
firestore.client().collection('parking_spots').document('C1').update(
  {'sensor_mac': 'A8:42:E3:46:F4:E0', 'camera_mac': '24:6F:28:47:F9:E8'})
print('C1 MACs restored')"
```

Heartbeats are recognized again on the next 20-second beat — no reflash needed.
