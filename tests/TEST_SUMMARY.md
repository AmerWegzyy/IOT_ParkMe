# ParkMe — Test Suite Summary & Results

**System under test:** the production ParkMe backend deployed on Google Cloud Run
(`https://parkme-backend-31114651685.me-west1.run.app`), with Firestore, Firebase Auth,
and Google Cloud Vision OCR — the same live system the dashboard and the real ESP32
hardware use.

**Bottom line: every test suite passes.** 31/31 deterministic checks succeed, the OCR
pipeline meets its accuracy benchmark on real photos, and the backend handles five
parking spots uploading images at the exact same instant with zero errors and zero
cross-spot interference.

| # | Suite | What it validates | Result |
|---|-------|-------------------|--------|
| 1 | `test_plate_extraction.py` | License-plate parsing logic (unit) | ✅ **12/12 pass** |
| 2 | `test_backend_parking_logic.py` | Heartbeat-vs-camera race ordering (unit) | ✅ **4/4 pass** |
| 3 | `test_lpr_pipeline.py` | End-to-end OCR on 30 real plate photos (cloud) | ✅ **27/30 exact reads (90%)** — meets the project benchmark; all 3 misses handled safely by design |
| 4 | `test_parallel_spots.py` | 5 spots uploading images **simultaneously** (cloud) | ✅ **15/15 pass, 0 cross-talk, 0 errors** |

All suites are pure-stdlib Python — no pip installs needed to reproduce any result.

---

## 1. Plate Extraction — `test_plate_extraction.py`

**What it tests:** the core parsing function that turns raw OCR text into a valid
Israeli license plate (7–8 digits). Includes adversarial cases designed to trick it:

- Clean 7- and 8-digit plates, and dashed Israeli formats (`12-345-67`, `123-45-678`)
- Plates surrounded by unrelated noise text and extra digit tokens
- **Traps that must be rejected:** 10-digit phone numbers (e.g. a "054-1234567" sign
  must not become a phantom plate), short digit fragments, and digits that would only
  form a plate if wrongly concatenated across separate lines
- Boundary validation of plate length limits

**Result:** ✅ **12/12 pass** (runs in under a second, fully offline)

```bash
python3 -m unittest tests.test_plate_extraction -v
```

## 2. Parking Logic — `test_backend_parking_logic.py`

**What it tests:** the trickiest timing logic in the backend — when a camera photo
and a sensor heartbeat arrive out of order (which genuinely happens on real hardware),
does the backend keep the right parking session?

- Preserves a fresh camera-first log instead of destroying it when the heartbeat lands
- Correctly discards stale logs from previous sessions
- Never resurrects terminal sessions (RESOLVED / REJECTED / ABORTED)
- Timezone-aware timestamp arithmetic

**Result:** ✅ **4/4 pass**

```bash
python3 -m unittest tests.test_backend_parking_logic -v
```

## 3. LPR Pipeline (End-to-End OCR) — `test_lpr_pipeline.py`

**What it tests:** the complete real-world recognition path. Each of the 30 photos of
real license plates in `test_pics/` is uploaded to the live cloud backend exactly the
way the ESP32-CAM uploads them (`POST /api/v1/sensors/park`, multipart). The backend
runs Google Cloud Vision OCR and must return the plate encoded in each filename.

**Result:** ✅ **27/30 exact reads — 90.0% accuracy** (full details in
`lpr_test_results.log`), meeting the project's on-record benchmark.

The 3 non-exact reads are the important part of the story: they are **known, documented
cases** (difficult photos), and the system's designed safety net catches them — an
unreadable plate never grants access. It instead routes to the **admin manual-review
flow** with the evidence photo attached, where the admin's Accept/Reject decision is
tested end-to-end elsewhere (see `Documentation/TESTING_GUIDE.md`). A recognition
system that fails *safe* is the correct engineering outcome for a gate-security system.

```bash
python3 tests/test_lpr_pipeline.py --server-url https://parkme-backend-31114651685.me-west1.run.app
```

## 4. Multi-Spot Parallelism — `test_parallel_spots.py`

**What it tests:** the rush-hour scenario — several cars arriving at once, several
camera nodes firing at once. Five simulated spots (A1, A2, B1, B2, C2) each send an
occupied heartbeat and then upload a **different** plate image at the **exact same
instant** (thread-barrier synchronized), through the same endpoints the real boards use.

The critical check is **cross-talk detection**: because every spot uploads a distinct
plate, if the backend ever returned spot X's plate to spot Y, it would prove concurrent
requests leak state between spots. It also measures throughput against a sequential
baseline, and verifies clean session lifecycle (every spot freed afterward, short stays
correctly logged as ABORTED per the 90-second rule).

**Result:** ✅ **15/15 correct plate attributions across 3 rounds — 0 cross-talk,
0 errors** (full details in `parallel_test_results.log`)

- Each of the 5 spots always received exactly its own plate back — perfect isolation
  under simultaneous load
- 5 simultaneous arrivals processed in **~2.9 s wall clock** vs ~8.4 s sequentially —
  a **2.9× concurrency speedup**, proving genuinely parallel request handling
- Live dashboard reflected all 5 spots flipping OCCUPIED (with their individual plates)
  and back to FREE in real time via SSE

```bash
python3 tests/test_parallel_spots.py --rounds 2 --baseline
```

---

## Beyond these suites

The Python suites above cover the backend and recognition pipeline. The rest of the
system is verified separately and documented:

- **Firmware logic:** compile-time `static_assert` tests
  (`ESP32/ParkMeFirmwareCompileTests/`) — threshold math, battery conversion, state
  classification, MAC parsing. A logic regression fails the build itself.
- **Hardware bring-up:** dedicated PASS/FAIL sketches for the ultrasonic sensor, OLED,
  and camera (`Unit Tests/`).
- **End-to-end and failure-recovery drills** on the real hardware (Wi-Fi loss, offline
  queueing, camera outage, calibration): procedures and expected timings in
  `Documentation/TESTING_GUIDE.md`.

*Latest results recorded 2026-07-17 against the live deployed backend. Every result in
this document is reproducible with the commands shown.*
