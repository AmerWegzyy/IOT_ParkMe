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
