# ParkMe Bug Triage & Fixes Interview (Grill Session)

**Date:** June 17, 2026

This document records the exact questions asked during the bug triage session and the authoritative answers provided by the project owner. It serves as the design spec for the applied fixes.

---

### Q1: 🔴 BUG-001: `SECRETS.h` is a completely wrong file — will not compile
**Question:** Your actual `SECRETS.h` contains leftover boilerplate from a Google Cloud Speech API example (`ssid`, `root_ca`, `ApiKey`). None of the `PARKME_*` constants exist, so both `.ino` sketches will fail to compile. Should I fix this by replacing `SECRETS.h` with a copy of `SECRETS.example.h` (with placeholder values for you to fill in)?
**Answer:** `do the required changes so everything works , you can delete every single piece of code in this project that related to HMAC signatures , it is no longer a requirement to have this additional security measures. update the markdown files so they do not list anything related to hmac signatures.`

### Q2: 🔴 BUG-003: `resolve_spot` broadcasts a timestamp without timezone
**Question:** The `resolve_spot` endpoint uses bare `datetime.now().isoformat()` instead of `get_il_time().isoformat()`. This produces a naive timestamp (no timezone info) that is inconsistent with every other endpoint and may display incorrectly on the frontend. Should I fix this?
**Answer:** `(Recommended) Yes, fix it — replace datetime.now() with get_il_time()`

### Q3: 🟠 BUG-004: `LPR_DEDUP_CACHE` grows unbounded — memory leak
**Question:** Every unique license plate is inserted into an in-memory dictionary and never removed. Over weeks of operation this will slowly consume all available RAM. Should I fix this?
**Answer:** `I DONT want the expiry time to be short , and i dont want it to affect other timings in my project since times are huge part and mightlead to edges cases , look for relevant timing issues , like heartbeat each 6 minutes and the hearbeat that a sensor sends and the bouncy driver (60 seconds interval) , and keep in mind we are running on google cloud so there might be delays , and select a good time for TTL ACCORDINGLY`
*(Agent implemented a 120-second TTL. This easily covers the ~45s maximum camera retry window, while remaining well below the 6-minute heartbeat to avoid interfering with long-term spot states.)*

### Q4: 🟠 BUG-005: Sensor heartbeat JSON still includes an unnecessary `spot_id` field
**Question:** The `makeHeartbeatPayload()` function in `ParkMeCommon.h` builds a JSON with both `mac_address` and `spot_id`. The backend ignores `spot_id` entirely. Additionally, `makeSpotUpdatePayload()` is dead code — never called anywhere. The `PARKME_SENSOR_SPOT_ID` constant in `SECRETS.example.h` is also now misleading since the backend resolves spots by MAC address. Should I clean all of this up?
**Answer:** `(Recommended) Yes, remove spot_id from makeHeartbeatPayload(), remove makeSpotUpdatePayload() (dead code), and remove PARKME_SENSOR_SPOT_ID from SECRETS.example.h`

### Q5: 🟠 BUG-006: `PARKME_GATE_SPOT_ID` still defined in `SECRETS.example.h`
**Question:** After the refactor to `camera_mac`, `PARKME_GATE_SPOT_ID` is no longer used by any firmware code but still exists in the example config file. Should I remove it?
**Answer:** `(Recommended) Yes, remove PARKME_GATE_SPOT_ID from SECRETS.example.h`

### Q6: 🟠 BUG-007: SSE client list is not cleaned up on disconnect
**Question:** The SSE event generator only removes the client from `sse_clients` on `asyncio.CancelledError`. If the client disconnects with a different exception (e.g., `ConnectionResetError`, `GeneratorExit`), the client dict stays in the list forever, and `broadcast_event()` keeps pushing messages into abandoned queues. Should I fix this?
**Answer:** `(Recommended) Yes, use a finally block so cleanup always runs regardless of disconnect reason`

### Q7: 🟠 BUG-008: Frontend auto-login uses a potentially expired token
**Question:** Firebase ID tokens expire after 1 hour. If a user returns the next day, the stale token in `localStorage` causes `initDashboard()` to fire, hit `GET /api/v1/users/me`, get a `401`, and then fall back to the login screen. This creates a brief visible flash of the dashboard before redirecting. Should I fix this?
**Answer:** `(Recommended) Yes, check the token's exp claim before calling initDashboard() to avoid the visual flash`

### Q8: 🟡 BUG-009: Documentation still references old `mac_address` schema
**Question:** Multiple docs still reference the old single `mac_address` field and the old `spot_id` camera form field. Should I update all of these?
**Answer:** `(Recommended) Yes, update all documentation files to reflect the sensor_mac / camera_mac schema`

### Q9: 🟡 BUG-010: `seed_firestore.py` does not wipe `users` or `vehicles` collections
**Question:** The seeder wipes `parking_spots` and `parking_logs` before re-seeding, but `users` and `vehicles` are left untouched. Since they use `.set()` with explicit IDs, re-runs won't create duplicates — but any manually-added test documents will persist. Should I add wipe calls for these collections too?
**Answer:** `No, the current behavior is fine since .set() is idempotent`

### Q10: 🟡 BUG-011: `GET /api/v1/logs` skips legitimate authorized parking events
**Question:** The admin logs endpoint only returns violations, unidentified, resolved, and aborted events. Normal successful parking events are silently skipped with `continue`. This means the admin cannot view a complete timeline of all parking activity. Is this intentional?
**Answer:** `No, the Security Log is intentionally for anomalies only — just add a comment documenting this`
