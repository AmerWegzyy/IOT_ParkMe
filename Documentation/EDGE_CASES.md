# ParkMe — Edge Cases the System Handles

> **Print 3 copies for the demo** (course requirement). Each row: what can go
> wrong, what the system does about it, and how to show it live.

## Connectivity & power failures

| # | Edge case | How ParkMe handles it | How to demo |
|---|---|---|---|
| 1 | **Sensor loses WiFi** | Detection + OLED keep working (network-independent core); dashboard marks the spot OFFLINE after the stale threshold and toasts the admin; auto-recovers on the next heartbeat after reconnect | Kill the hotspot; watch OLED keep updating; restore and watch the card recover |
| 2 | **Car parks while sensor is offline** | State change saved to NVS **flash** (survives even a power cut); flushed to the backend within seconds of reconnect | Kill WiFi → place object → (optionally power-cycle the board) → restore WiFi → dashboard flips OCCUPIED |
| 3 | **Car parks AND leaves while offline** | Only the latest state is flushed — the backend is never stuck "occupied" (single-slot queue, documented design choice) | Kill WiFi → object in → object out → restore → spot stays FREE |
| 4 | **Camera offline when a car arrives** | Photo is still **taken at the moment of arrival** and held in memory; sensor re-broadcasts OCCUPIED every 2 s; after reconnect the camera uploads the *original arrival photo* — and discards it if the car already left; meanwhile a missing-photo manual review opens after 30 s | Unplug camera WiFi → trigger sensor → restore → original photo arrives; review opened at +30 s |
| 5 | **Backend restarts (Cloud Run)** | All state lives in Firestore, not process memory; dashboard SSE and board streams auto-reconnect | Deploy/restart the service mid-demo; dashboard recovers alone |
| 6 | **Dashboard loses network** | Connection dot turns red; SSE reconnects in ~3 s; a 5-second polling safety net refreshes the grid; no duplicate or frozen entries | Toggle laptop WiFi for ~20 s |

## Recognition & authorization edge cases

| # | Edge case | How ParkMe handles it | How to demo |
|---|---|---|---|
| 7 | **Plate can't be read** (blank paper, bad angle) | No guess is made — spot enters **manual review** with the evidence photo; admin Accept → welcome; Reject → violation with photo attached permanently; OLED shows the outcome | Trigger with blank paper; resolve from the admin dashboard |
| 8 | **No photo at all** (camera dead/covered) | Missing-photo review opens automatically 30 s after the occupied heartbeat | Cover the lens and trigger |
| 9 | **Unregistered car** | ACCESS DENIED on OLED + red violation entry with "Show Picture" evidence in the Security Log | Use an unregistered valid-format plate |
| 10 | **Registered car, wrong zone** (e.g., lecturer in a student spot) | Denied + violation logged; **admins are authorized everywhere** | Lecturer plate on the student spot |
| 11 | **Phone number / sticker text near the plate** | 10-digit sequences and cross-line digit joins are rejected — no phantom plate; falls to manual review instead | Show a page with "054-1234567" |
| 12 | **Camera retries the same frame** (up to 3×) | Deduplication — one session, one log entry, no duplicate violations | Visible in logs during any capture |
| 13 | **Photo arrives before the heartbeat** (race) | 10-second grace window preserves the camera-first log instead of destroying the session | Happens naturally; covered by unit tests |
| 14 | **Driver leaves within 90 s** ("bouncy driver") | Session converted to ABORTED — statistics aren't polluted with drive-throughs | Trigger, wait for WELCOME, remove the object early |

## Scale & operations

| # | Edge case | How ParkMe handles it | How to demo |
|---|---|---|---|
| 15 | **Several cars arrive at the same instant** | Backend processes simultaneous uploads concurrently with zero cross-spot leakage — verified 15/15 with 5 spots uploading in the same instant (~3 s total, 2.9× faster than serial; see `tests/TEST_SUMMARY.md`) | `python3 tests/test_parallel_spots.py` with the dashboard open |
| 16 | **Calibration with nothing in range** | CALIBRATE FAIL ("target too far" / "no echo"); previous threshold kept; successful calibration **persists across power cycles** (flash) | Calibrate at empty air, then at 15 cm; power-cycle and verify |
| 17 | **Role-based data privacy** | Enforced server-side, not just hidden UI: students see only student spots and never plates; `/api/v1/logs` returns 403 for non-admins | Log in as student; show the 403 in dev tools |

## Recently hardened (found and fixed on real hardware)

| # | Edge case | How ParkMe handles it | How to demo |
|---|---|---|---|
| 18 | **Same spot re-occupied within seconds of the previous car leaving** | The camera's single-slot ESP-NOW mailbox could miss a "car left" message that arrived while it was still busy processing the previous car, leaving its per-cycle capture latch stuck so the next car was never photographed. The sensor now tags every state broadcast with a sequence number; the camera detects a new occupancy cycle whenever that number changes (even if it never saw the FREE in between) and resets automatically, guaranteeing every car gets a photo | Quickly swap two different plates on the same spot back-to-back with no pause; confirm both are photographed and logged as separate sessions |
| 19 | **WiFi outage lasts more than ~1 minute** | ESP-NOW only delivers between radios on the same WiFi channel. During a long outage the SDK's background reconnect kept scanning channels, so the sensor and camera radios eventually drifted apart and stopped hearing each other — the camera appeared to "stop working" only on long outages, not short ones. Both boards now remember the AP's channel and re-pin their radio to it after every failed reconnect attempt, so sensor→camera triggers keep working for the whole outage, however long it lasts | Kill WiFi for 2+ minutes; place a car; the OLED and serial still show the ESP-NOW trigger and capture happening throughout ("Radio pinned to channel N" in serial); restore WiFi and watch it catch up |
| 20 | **Car leaves and a new car arrives during the same WiFi outage** | The sensor's single-slot pending-telemetry queue could drop a car's "left" event when it was overwritten by the next car's "arrived" event before WiFi returned. The backend never learned the first car left, so it kept that session open — and silently discarded the second car's photo as "already processed" for a car that was gone. The sensor now remembers a dropped car-left event and delivers it first on reconnect, closing the old session before the new arrival is processed (with a backend-side check as a second line of defense for the reverse timing) | Occupy the spot → disconnect WiFi → free the spot → occupy again with a different plate, still offline → reconnect WiFi → confirm the new car's session and photo appear, not the old one |
| 21 | **Israeli plate's blue "IL" country band** | OCR sometimes reads the "IL" band as a stray digit, and the old text-joining logic glued that phantom digit onto the real plate number (e.g. a genuine 7-digit plate misread as an 8-digit one). Extraction now drops any token that mixes letters with digits and discards a lone leading "1" whenever the remaining digits already form a valid plate on their own | Present a real Israeli plate with the visible IL band in frame; confirm the extracted plate matches the real number with no extra leading digit |
