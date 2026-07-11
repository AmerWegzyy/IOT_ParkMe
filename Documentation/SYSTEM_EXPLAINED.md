# ParkMe — How the Whole System Works (Deep Dive)

The one document that explains every design decision and mechanism in the project: the hardware, ESP-NOW, calibration, WiFi-loss handling, memory/buffers, the dual-core design, how the boards talk to each other and to the cloud — and **why** we built it this way. Use it to prepare presentations and to answer examiners' questions.

---

## 1. The Big Picture

```
 ┌────────────────── PARKING SPOT ──────────────────┐        ┌───────── GOOGLE CLOUD ─────────┐
 │                                                  │        │                                │
 │  ┌─────────────┐   ESP-NOW    ┌───────────────┐  │  HTTPS │  ┌──────────┐   ┌───────────┐ │
 │  │ SENSOR NODE │ ───────────► │  CAMERA NODE  │──┼───────►│  │ FastAPI  │──►│ Cloud     │ │
 │  │ ESP32       │  (no router) │  ESP32-CAM    │  │  photo │  │ backend  │   │ Vision OCR│ │
 │  │ HC-SR04     │ ◄─────────── │  OV2640       │  │        │  │(Cloud Run)│  └───────────┘ │
 │  │ OLED screen │    acks      └───────────────┘  │        │  └────┬─────┘                 │
 │  └──────┬──────┘                                 │        │       │                       │
 │         │ HTTPS: heartbeats up, screen msgs down │        │  ┌────▼─────┐                 │
 │         └────────────────────────────────────────┼───────►│  │ Firestore│                 │
 └──────────────────────────────────────────────────┘        │  └────┬─────┘                 │
                                                             └───────┼───────────────────────┘
                                              Firebase Hosting ◄─────┘ SSE (live push)
                                              web dashboard (admin + users)
```

**The story of one car:** the ultrasonic sensor sees the distance drop below its calibrated trigger → the sensor node instantly messages the camera node over ESP-NOW (direct radio, ~2 ms, no router needed) → the camera takes one photo and uploads it over HTTPS to the backend on Cloud Run → the backend runs Google Vision OCR, extracts a valid 7–8-digit Israeli plate, looks up the vehicle's owner and compares their role to the spot's category → the verdict (WELCOME / ACCESS DENIED) is pushed two ways at once: over SSE to the sensor node's OLED, and over SSE to every open dashboard. Firestore records the session; when the car leaves, the next heartbeat closes the log with an exit time.

---

## 2. Why Two Boards? Why ESP-NOW and Not Cables or One Board?

This is the most common examiner question. The honest engineering rationale:

**Why not one ESP32-CAM doing everything (ultrasonic + camera + screen)?**
- The AI-Thinker ESP32-CAM has almost **no free GPIO pins** — the OV2640 camera consumes most of them, GPIO0 is a boot-strapping pin, GPIO4 drives the flash LED, and the pins that remain conflict with I2C. Wiring an ultrasonic sensor *and* an I2C OLED alongside the camera is physically impractical on that module.
- The camera's job is bursty and heavy: a TLS handshake plus a ~50–130 KB upload can block for seconds. Real-time sensing (every 500 ms) and instant screen feedback must never freeze behind an upload. Splitting the roles across two chips is the hardware version of "separation of concerns."
- One board is a single point of failure; with two, a camera fault still leaves live occupancy tracking working (and vice versa — proven in our failure testing).

**Why not connect the two boards with wires (UART/I2C)?**
- The two devices don't live in the same place: the sensor points at the parking surface; the camera needs line-of-sight to a license plate. Metres of signal cable in an outdoor parking lot means conduit, connectors, corrosion, and noise pickup on the lines — real installation cost and fragility.
- A wired link fixes the topology forever. With radio, one camera can serve re-positioned or additional sensors without re-cabling (our protocol already carries the spot ID in every message).

**Why ESP-NOW specifically, and not WiFi/HTTP between the boards?**
- **No router in the loop:** ESP-NOW is a direct ESP32-to-ESP32 protocol on the WiFi radio. During our WiFi-outage tests, the trigger chain kept working with the router off — the car still got photographed. HTTP between boards would die with the router.
- **Latency:** an ESP-NOW frame arrives in ~1–2 ms. The alternative (camera polls the server, server was told by the sensor) — our original design — added 1–7 s per event. This is why we call the current architecture *edge-push*.
- **It's free:** both chips already have the radio; ESP-NOW coexists with the normal WiFi connection on the same interface (the camera receives triggers *and* uploads over WiFi).
- The 250-byte ESP-NOW frame limit is irrelevant for us — our state message is a compact struct.

**Reliability layers on the ESP-NOW link:** every message carries a magic number + protocol version (garbage/foreign frames are dropped), a **sequence number** (duplicate triggers for the same cycle are ignored), and the camera replies with explicit **acks** (`capture_queued`, `capture_started`, `capture_completed`, `capture_failed`, `spot_freed`) that the sensor shows on its OLED. The sensor sends both **unicast** (to the configured camera MAC) and **broadcast**, and re-announces the current state every **2 seconds** — this re-broadcast is also the retry engine after a failed capture.

---

## 3. Inside the Sensor Node: Dual-Core FreeRTOS

The ESP32 has two CPU cores, and we split the work explicitly:

| Core 0 — `networkTask` | Core 1 — Arduino `loop()` |
|---|---|
| WiFi status watching | Ultrasonic sampling (every 500 ms, 3-sample average) |
| HTTPS heartbeats + queued telemetry | Occupancy classification |
| SSE stream to receive display commands | OLED rendering (framebuffer → I2C) |
| Display poll fallback + result acks | ESP-NOW state broadcasts to the camera |
| | Calibration button (4-second hold) |

The two cores share state through a small struct protected by a **FreeRTOS mutex** (`sharedStateMutex`) — network status flows one way, display commands the other. The rule that falls out of this design: **the screen and the sensing never block on the network.** A slow TLS handshake, a dead router, a hung server — the OLED still updates twice a second and cars are still detected. This is also why the verdict screen feels instant: the display command arrives on Core 0 via SSE and Core 1 renders it on its next pass.

---

## 4. Memory and Buffers (where the bytes actually live)

| Buffer | Where | Size | Why it exists |
|---|---|---|---|
| Camera frame buffers | ESP32-CAM PSRAM (driver-owned, `fb_count` ≈ 2) | ~50–130 KB each (VGA JPEG) | The OV2640 driver fills these; **we always do two dummy `esp_camera_fb_get()`/return cycles before the real grab** to flush stale frames out of the FIFO — otherwise you upload a photo of the *previous* car |
| **Persisted photo** | PSRAM via `ps_malloc` (heap fallback) | one JPEG | The arrival-moment photo is **copied out of the driver buffer** so it survives a WiFi outage; the exact same bytes are re-sent after reconnection instead of re-photographing. Freed when the server answers, or when the spot goes free (never send a photo of a car that already left) |
| Pending telemetry | Sensor **NVS flash** | a few bytes | The latest unsent state change; survives even power loss, flushed on reconnect |
| Calibration threshold | Sensor **NVS flash** (`thr_cm`) | 4 bytes | The technician-set trigger distance; loaded on every boot |
| OLED framebuffer | Sensor RAM | 1 KB (128×64÷8) | We drive the SSD1306 at register level with our own font table and `setPixel` — no display library |
| Multipart upload | Camera RAM (streamed) | headers only | The JPEG body is written straight from the photo buffer to the socket — never duplicated into a request string |

PSRAM note: the AI-Thinker board has 4 MB PSRAM, so persisting one JPEG is trivial. On a PSRAM-less board the firmware automatically drops to a smaller frame size and the copy falls back to internal heap; if even that allocation fails, the code degrades to the old behavior (retry with a fresh capture on the next 2-second ping) rather than crashing.

---

## 5. Calibration — "Set the Trigger by Demonstration"

The technician physically shows the sensor what "a parked car" means:

1. Place any object at the exact distance where a car should be detected (**3–50 cm**).
2. Hold the calibration button (GPIO13 → GND, internal pull-up — two wires, no resistor) for **4 seconds** while the node runs. No reflash, no computer.
3. The node averages **15 samples** (invalid/no-echo readings excluded), adds a **2 cm margin**, clamps to [3, 50] cm, and stores the result in NVS flash.
4. OLED feedback: `CALIBRATE PASS / TRIGGER 37CM` — or `CALIBRATE FAIL` (`NO ECHO` / `TARGET TOO FAR`) with the previous value kept.

Why these numbers: the HC-SR04 physically cannot measure below ~3 cm; 50 cm is the ceiling so calibrating against a far wall by accident is impossible (it fails loudly instead). The stored threshold survives reboots and power loss, is unique per node, and is the exact value the classifier uses every 500 ms: `distance ≤ threshold → OCCUPIED`, `≤ max-reliable (350 cm) → FREE`, else `UNKNOWN` (invalid readings are *discarded*, never transmitted — noise cannot flip a spot's state).

---

## 6. WiFi Loss — What Happens at Every Layer

Tested live on hardware. The design goal: **a network outage must never lose an event or show wrong availability.**

| Layer | During the outage | On recovery |
|---|---|---|
| Sensor sensing/OLED | Unaffected (Core 1 is network-free) | — |
| Sensor → camera trigger | **Unaffected** (ESP-NOW needs no router) | — |
| Sensor telemetry | Latest state change saved to NVS (survives power cuts) | Flushed within ~1 s of reconnect; SDK auto-reconnect rejoins the AP |
| Sensor display stream | SSE drops; reconnect backoff 3→30 s | Poll fallback picks up any stored command; missed verdicts are held server-side |
| **Camera photo** | Photo **is still taken at the arrival moment** and persisted in PSRAM; serial: "Photo saved; will send after reconnect" | The sensor's 2-second OCCUPIED re-broadcast re-triggers the upload of the **same** photo (serial: "Reusing photo captured earlier this cycle"). If the car left meanwhile, the stale photo is discarded (`spot_freed`) |
| Camera WiFi | Explicit retry every 5 s + SDK auto-reconnect | — |
| Backend view | `last_seen` stops advancing; nothing breaks | Ordering guards (10 s camera-first grace, `should_preserve_recent_active_log`) prevent scrambled-arrival corruption — unit-tested |
| Dashboard | After **120 s** of silence the spot turns **OFFLINE** (never "confidently FREE") + one admin toast; offline spots are excluded from recommendations | Next heartbeat flips it back + recovery toast |

Known, documented limitations: the NVS queue holds only the *latest* state (a park-and-leave entirely inside a long outage is collapsed to its end state); offline alerts render only in an open dashboard (staleness is computed client-side).

---

## 7. How the Boards Talk to the Server

Plain REST + SSE over HTTPS (TLS 443 to Cloud Run; plain HTTP for local development — one scheme constant in `SECRETS.h` switches everything):

| Call | Direction | Purpose |
|---|---|---|
| `POST /api/v1/sensors/heartbeat` | sensor → server | `{mac, is_occupied, battery}` every 20 s + instantly on change; server maps MAC → spot, updates Firestore, broadcasts SSE |
| `POST /api/v1/sensors/park` | camera → server | multipart JPEG + camera MAC; server runs OCR → authorization → verdict in the HTTP response |
| `GET /api/v1/displays/stream` | server → sensor (SSE) | Verdict/screen commands pushed with zero latency |
| `POST /api/v1/displays/poll` / `result` | sensor → server | Poll fallback while SSE is reconnecting; delivery acknowledgements |
| `GET /api/v1/stream?token=…` | server → browser (SSE) | Live spot updates + (admins only) security log events |

Identity model: boards are identified by their **WiFi MAC address**, mapped to spot documents in Firestore — flashing a replacement board only requires updating one Firestore field, not the firmware. (Honest caveat: MAC-trust means the hardware endpoints are unauthenticated — acceptable for a course prototype, flagged as a pilot blocker in the audit.)

### The server's brain — decision layers on one photo

1. OCR (two Vision modes, fallback) → keep only a **plausible plate**: contiguous digit groups, exactly 7–8 digits — a permit sticker or phone number in frame can never be merged into a phantom plate (12 unit tests + a 31-image live suite, 90.3% exact match).
2. Plate → `vehicles` → `users` → compare role to spot category (server-side; admins pass everywhere).
3. Outcomes: WELCOME (5 s screen) / DENIED + violation log with the photo as evidence / unreadable → **manual review**: admin sees the photo on the dashboard and clicks Accept or Reject — the system *fails closed*, never auto-approves.

### Timing/state windows worth knowing in the defense

| Window | Value | Meaning |
|---|---|---|
| Camera-first grace | 10 s | A photo may legitimately arrive before the heartbeat; don't let the heartbeat clobber it |
| Photo deadline | 30 s | Occupied heartbeat with no photo → ghost log → manual review |
| Bouncy driver | 90 s | Park-and-leave under 90 s becomes `ABORTED`, not a real session |
| Dashboard staleness | 120 s | No heartbeat → spot rendered OFFLINE |
| Sentinel plates | — | The `license_plate` field doubles as workflow state: `UNIDENTIFIED`, `MANUAL_ACCEPTED`, `REJECTED`, `RESOLVED`, `ABORTED` |

### Why the cloud is pinned to exactly one instance

SSE client queues and the display command store live in process memory, so `cloudbuild.yaml` deploys with `--max-instances=1 --min-instances=1 --timeout=3600`: one always-warm instance (no cold start to break the camera's 7 s timeout), hour-long SSE connections allowed, and no second instance that would see an empty command store. The trade-off (no horizontal scaling) is deliberate and documented.

---

## 8. Design-Decision FAQ (fast answers for examiners)

- **Why edge-push instead of the camera polling the server?** 1–7 s latency dropped to ~2 ms, and the trigger path survives router outages.
- **Why Firestore and not SQL?** Real-time-friendly, zero-ops, free tier, and the backend needs document lookups (MAC → spot, plate → user), not joins. Schema constraints are enforced in code.
- **Why store evidence photos as base64 inside the log document?** One write, one read, no Storage-bucket ACL surface; VGA JPEGs (~50–130 KB) fit comfortably under Firestore's 1 MiB doc limit.
- **Why a hand-rolled OLED driver and font?** The SSD1306 libraries clashed with our pin/offset variant; 1 KB framebuffer + a 5×7 font table we control (which is also how we found and fixed the upside-down-digit glyph bug).
- **Why digits-only plates?** Israeli plates are 7–8 digits; validating the format server-side rejects OCR noise instead of accusing innocent drivers.
- **Why does calibration set the distance directly instead of measuring the empty spot?** First version derived `threshold = empty-baseline − 30 cm`; at short mounting distances the subtraction collapsed to the minimum floor and confused everyone. "Put the target where the car will be" is simpler to teach, works at 3–50 cm, and is what a technician actually wants.
- **What's the weakest part?** (Be honest — examiners respect it.) Hardware endpoints trust MACs without authentication; offline/low-battery alerting is dashboard-only; incentive points are not implemented. All catalogued with fixes in `USER_STORY_IMPLEMENTATION_AUDIT.md`.

---

## 9. Where to Go Next

- **Run and test it:** `TESTING_GUIDE.md` (scenarios, failure drills, demo-day checklist)
- **Simulate a full parking lot with one set of hardware:** `Backend/simulate_spots.py` (see TESTING_GUIDE §"Multi-spot simulation")
- **Every endpoint, schema, and timing:** `PROJECT_OVERVIEW.md`
- **Deploy/operate the cloud:** `step_by_step_deployment.md`, `CLOUD_DEPLOYMENT_GUIDE.md`, `cloud_setup_complete_guide.md`
- **Requirements & audit:** `USER_STORIES.md`, `USER_STORY_IMPLEMENTATION_AUDIT.md`
