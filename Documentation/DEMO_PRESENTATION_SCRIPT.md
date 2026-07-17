# ParkMe — Staff Demo Script (What to Do and What to Say)

A complete run-of-show for presenting the project: setup checklist, the live demo scenario with speaking notes, the testing story, and the parallel multi-spot test logs. Total time: ~15 minutes + Q&A.

---

## 0. Before the Staff Arrive (15-minute checklist)

| ✔ | Item |
|---|---|
| ☐ | **George hotspot ON** before powering the boards (SECRETS.h is set to `George` / `george2003`) |
| ☐ | Power the **sensor node** → OLED shows free state; serial (optional): heartbeats returning 202 |
| ☐ | Power the **camera node** → serial shows `Gate spot: C1` and WiFi connected |
| ☐ | Dashboard open as **admin** (`admin@technion.ac.il` / `password123`) at <https://parkme-technion-f280b.web.app> — C1 is FREE with fresh last-seen |
| ☐ | Second browser tab logged in as **student** (`student@technion.ac.il`) for the role-visibility segment |
| ☐ | Printed plate photos ready: registered plate `1234567` (WELCOME), lecturer plate `9876543` (DENIED on C1), and one blank page (manual review) |
| ☐ | Laptop terminal open in the repo folder, ready to run the simulator |
| ☐ | **Nobody runs `seed_firestore.py`** (it wipes the real hardware MACs). If C1 shows OFFLINE, use the recovery snippet in `TESTING_GUIDE.md` §9 |

**Golden demo rhythm (prevents every timing surprise):** occupy → wait for the verdict on the OLED (~5–10 s) → free → pause 10 s → next cycle. Never remove the "car" between "Capturing..." and the verdict.

---

## 1. Opening Pitch (2 minutes — no hardware yet)

Say something like:

> "ParkMe is a smart-parking system for reserved campus spots. Each spot has two ESP32 boards: an ultrasonic **sensor node** that detects the car and drives a driver-facing screen, and a **camera node** that photographs the license plate. The moment a car parks, the sensor triggers the camera directly over **ESP-NOW** — board-to-board radio, no router involved, about 2 milliseconds. The camera uploads the photo over HTTPS to our **FastAPI backend on Google Cloud Run**, which runs **Google Vision OCR**, checks the plate owner's role against the spot's category in **Firestore**, and pushes the verdict two ways at once: to the driver's screen and to every open dashboard, live over **SSE**."

Then one sentence of honesty that staff always respect:

> "We'll show the happy path, the failure handling — including WiFi loss — and the automated test suite we built."

**If asked "why two boards / why ESP-NOW?"** — the full answers are rehearsed in `SYSTEM_EXPLAINED.md` §2 and §8. Short version: the ESP32-CAM has no free pins for sensors and a screen; uploads must never block real-time sensing; ESP-NOW survives router outages and costs 2 ms instead of seconds of polling.

---

## 2. Live Demo — the Scenario (6–7 minutes)

### Scene 1 — Live availability (30 s)
Show the dashboard: C1 FREE, battery %, fresh last-seen.
> "The sensor heartbeats every 20 seconds, and instantly on any change. What you see is live — not polling; the server pushes over SSE."

### Scene 2 — Authorized driver → WELCOME (2 min)
Hold the **registered plate** (`1234567`) in front of the camera, then place the object in front of the sensor.
> "The sensor just detected occupancy and triggered the camera over ESP-NOW — watch the screen."

Wait for the OLED: **WELCOME**. Point at the dashboard: C1 flipped to OCCUPIED with the plate shown, within ~2 seconds.
> "That whole chain — detection, radio trigger, photo, cloud OCR, authorization, verdict on the screen — took a few seconds, fully automatic."

**Leave this car parked** (it becomes the >90 s "real session" for Scene 5). Use the golden rhythm for every later cycle.

### Scene 3 — Unauthorized driver → violation (1.5 min)
*(Do this on a later cycle after freeing Scene 2's car — or explain from the Security Log if time is short.)*
Show the **lecturer plate** (`9876543`) on student spot C1 → OLED: **ACCESS DENIED**; dashboard Security Log gets a red violation entry.
> "The plate is registered — but to a lecturer, and this is a student spot. Role checks run **server-side**; the photo is attached to the violation as evidence."

Click **Show Picture** so they see the evidence photo.

### Scene 4 — Unreadable plate → manual review (1.5 min)
Show a **blank page** to the camera and trigger the sensor.
> "OCR can't find a valid Israeli plate — 7 or 8 digits. The system **fails closed**: it never guesses and never auto-approves. It opens a manual review for the admin."

On the dashboard: review entry with the photo → click **Accept** → OLED shows the welcome.
> "A human decision, with the photo in front of them, in seconds."

### Scene 5 — The car leaves (30 s)
Remove Scene 2's object (after it was parked >90 s).
> "The session closes with an exit time — that's what feeds the usage statistics."

*(If a short-stay cycle logs **ABORTED**, own it: "under 90 seconds we treat it as a driver who changed their mind — a deliberate filter so statistics aren't polluted by people bouncing in and out.")*

### Scene 6 — The killer feature: WiFi loss (optional but powerful, 2 min)
Turn the George hotspot **off**. Place a car + plate.
> "The router is dead — but the sensor still triggers the camera, because ESP-NOW doesn't need it. The camera takes the photo **right now**, at the moment of arrival, and persists it in PSRAM."

Turn the hotspot back on, wait a few seconds:
> "Reconnected — and it uploads **the same photo it took during the outage**, not a new one. No event was lost."

---

## 3. The Testing Story (3 minutes — talk over a terminal)

> "We didn't just test by hand — the project has an automated test suite at three levels."

**Level 1 — unit tests (run it live, takes 1 second):**
```powershell
python -m unittest tests.test_plate_extraction tests.test_backend_parking_logic -v
```
> "21 tests covering the plate-extraction rules — including OCR traps we found on real hardware, like the blue IL band being misread as a digit 1, phone numbers in frame, and permit stickers — plus the heartbeat-versus-camera race-ordering logic."

**Level 2 — real-image OCR pipeline:**
> "We ran **31 real plate photos** through the live endpoint — 90% exact plate match; the failures fall safely to manual review instead of guessing." (`tests/test_lpr_pipeline.py` — don't run it live, it writes real logs.)

**Level 3 — firmware compile-time tests:**
> "Threshold math, battery conversion and state classification are `static_assert`s — a logic regression won't even compile." (`ESP32/ParkMeFirmwareCompileTests/`)

**Failure drills:** point at `TESTING_GUIDE.md` §5.
> "We drilled the failure modes on real hardware: sensor offline, camera offline mid-capture, parking during an outage, backend restart. Every drill has an expected recovery path, and offline spots show as OFFLINE — never as falsely free."

---

## 4. The Parallel Multi-Spot Test (2 minutes — the simulator logs)

We own one physical spot, so we proved the **whole lot** works with a simulator my partner ran against the live backend — five simulated spots (A1, A2, B1, B2, C2) sending **real heartbeats and real photos through the exact endpoints the hardware uses**, in parallel with the real C1 hardware.

**Option A — run it live (best):**
```powershell
python Backend/simulate_spots.py --fast
```
Put the dashboard on the projector:
> "Every spot you see arriving, being photographed, OCR'd, authorized, and leaving is going through the same production pipeline as the real hardware next to me — the backend can't tell the difference. This is how we tested concurrency: multiple spots, parallel sessions, live SSE updates, one backend."

Point out in the terminal log: heartbeats with battery levels, photo uploads with the OCR'd plate in the response, cars arriving/leaving on independent timers.

**Option B — show the saved logs:** open the terminal output my partner captured from a previous run alongside the matching Security Log entries in the dashboard, and make the same point: parallel sessions, same pipeline, per-spot state independent.

*(Extra flex if asked about monitoring: `python Backend/simulate_spots.py --offline-demo A2` makes a simulated sensor die mid-run — after 120 s the dashboard flags it OFFLINE, then it recovers.)*

---

## 5. Closing + Hard Questions (1 minute)

> "To summarize: edge-push architecture — milliseconds from detection to camera; cloud OCR and server-side authorization; live dashboards over SSE; failure-tested on real hardware; and an automated test suite from unit level to a 31-image OCR benchmark."

Be ready for (full answers in `SYSTEM_EXPLAINED.md` §8):
- **Why ESP-NOW and not cables or one board?** → pins, blocking uploads, router-independence.
- **How did you calibrate?** → by demonstration: place a target at the desired trigger distance (3–50 cm), hold the button 4 s; stored in flash per node. Offer to show it live — it's a 20-second demo.
- **What happens if OCR fails an authorized driver?** → manual review, fail-closed, admin approves with the photo in view.
- **What's the weakest part?** → answer honestly: hardware endpoints trust MAC addresses without authentication, offline alerting is dashboard-only. "Both are catalogued with fixes in our audit document." Staff reward honesty here.

---

## 6. If Something Breaks Mid-Demo

| Symptom | Fix |
|---|---|
| C1 shows OFFLINE, boards look fine | Someone reseeded Firestore — run the MAC-restore snippet in `TESTING_GUIDE.md` §9 (20 seconds, no reflash) |
| No verdict appears on OLED | Check camera serial; if WiFi dropped, turn the segment into Scene 6 — "let me show you what happens on WiFi loss" |
| Photo/verdict feels slow | Keep talking through the pipeline ("TLS handshake on a microcontroller, cloud OCR…") — 5–10 s is normal and worth narrating, not hiding |
| Whole hotspot fails | ESP-NOW still triggers + photo persists → recover when hotspot returns; meanwhile run the simulator against the cloud from the laptop's own connection |
