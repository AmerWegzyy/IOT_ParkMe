# ParkMe Bug Report

**Generated:** 2026-06-17T19:56 IST  
**Scope:** Full codebase audit (Backend, Frontend, ESP32 firmware, Database seeder, Documentation)

---

## 🔴 Critical Bugs

### ✅ [RESOLVED] BUG-001: `SECRETS.h` is a completely wrong file — will not compile
**File:** [SECRETS.h](file:///mnt/c/Users/aamer/OneDrive/Desktop/TECHNION/SEMESTER6/IOT/parkme_project/IOT_ParkMe/ESP32/SECRETS.h)  
**Severity:** 🔴 Critical (Compilation blocker)

The actual `SECRETS.h` used by the project contains leftover boilerplate from a Google Cloud Speech API example. It defines `ssid`, `password`, `server`, `root_ca`, and `ApiKey` — none of which match the constants that the firmware expects (e.g., `PARKME_WIFI_SSID`, `PARKME_SERVER_HOST`, `PARKME_GATE_TRIG_PIN`, etc.).

Both `ParkMeSensorNode.ino` and `ParkMeCameraNode.ino` include this file via `ParkMeConfig.h → SECRETS.h` and will **fail to compile** because every `PARKME_*` constant is undefined.

**Fix:** Replace the contents of `SECRETS.h` with a copy of `SECRETS.example.h`, then fill in the real WiFi credentials and server address.

---

### ✅ [RESOLVED] BUG-002: HMAC verification silently passes when headers are missing
**File:** [main.py:100-106](file:///mnt/c/Users/aamer/OneDrive/Desktop/TECHNION/SEMESTER6/IOT/parkme_project/IOT_ParkMe/Backend/main.py#L100-L106)  
**Severity:** 🔴 Critical (Security bypass)

```python
async def verify_hmac_signature(request: Request):
    signature = request.headers.get("X-Signature")
    timestamp = request.headers.get("X-Timestamp")
    
    if not signature or not timestamp:
        return  # ← Silently passes!
```

If the ESP32 (or any attacker) sends a request **without** `X-Signature` and `X-Timestamp` headers, the function returns early without raising an exception. This means the heartbeat and bulk endpoints are effectively **unprotected** — anyone can spoof sensor data by simply omitting the HMAC headers entirely.

**Fix:** Change the early return to `raise HTTPException(status_code=401, detail="Missing HMAC headers")` once HMAC is enforced. This is noted as a to-do item, but the current behavior is a silent security hole that should be explicitly documented with a comment.

---

### ✅ [RESOLVED] BUG-003: `resolve_spot` broadcasts a timestamp without timezone
**File:** [main.py:650](file:///mnt/c/Users/aamer/OneDrive/Desktop/TECHNION/SEMESTER6/IOT/parkme_project/IOT_ParkMe/Backend/main.py#L650)  
**Severity:** 🔴 Critical (Inconsistency)

```python
"timestamp": datetime.now().isoformat(),  # ← No timezone!
```

Every other endpoint uses `get_il_time()` to produce timezone-aware `Asia/Jerusalem` timestamps. But the `resolve_spot` endpoint uses bare `datetime.now()` (naive, no timezone), which produces a different format from everything else and will display incorrectly on the frontend.

**Fix:** Replace `datetime.now().isoformat()` with `get_il_time().isoformat()`.

---

## 🟠 Medium Bugs

### ✅ [RESOLVED] BUG-004: `LPR_DEDUP_CACHE` grows unbounded — memory leak
**File:** [main.py:91](file:///mnt/c/Users/aamer/OneDrive/Desktop/TECHNION/SEMESTER6/IOT/parkme_project/IOT_ParkMe/Backend/main.py#L91)  
**Severity:** 🟠 Medium (Production stability)

```python
LPR_DEDUP_CACHE = {}
```

Every unique license plate that passes through the camera is inserted into this dictionary and **never removed**. Over weeks/months of operation, this dictionary will grow indefinitely, consuming server RAM. In a Cloud Run deployment with limited memory (256MB–512MB), this could eventually cause the container to be killed by the OOM killer.

**Fix:** Implement a periodic cleanup (e.g., purge entries older than 30 seconds on each request), or replace with a TTL-based cache like `cachetools.TTLCache`.

---

### ✅ [RESOLVED] BUG-005: Sensor heartbeat JSON still includes an unnecessary `spot_id` field
**File:** [ParkMeCommon.h:135-149](file:///mnt/c/Users/aamer/OneDrive/Desktop/TECHNION/SEMESTER6/IOT/parkme_project/IOT_ParkMe/ESP32/ParkMeCommon/ParkMeCommon.h#L135-L149)  
**Severity:** 🟠 Medium (Architectural debt)

The `makeHeartbeatPayload()` function builds a JSON that includes both `mac_address` AND `spot_id`:
```json
{"mac_address":"AA:BB:CC:DD:EE:01","spot_id":101,"is_occupied":true,"battery_level":95}
```

The backend's Pydantic `HeartbeatPayload` model only declares `mac_address`, `is_occupied`, and `battery_level` — so `spot_id` is silently ignored. However, this is misleading: a developer reading the C++ code would assume the backend uses the `spot_id`, and the `PARKME_SENSOR_SPOT_ID` constant in `SECRETS.example.h` reinforces this false assumption. The integer `101` also doesn't match the string document IDs used in Firestore (e.g., `"A1"`, `"C1"`).

**Fix:** Remove the `spot_id` field from `makeHeartbeatPayload()` and the `PARKME_SENSOR_SPOT_ID` constant from `SECRETS.example.h`. The `makeSpotUpdatePayload()` function (lines 122-133) also appears to be dead code — it is never called anywhere and should be removed.

---

### ✅ [RESOLVED] BUG-006: `PARKME_GATE_SPOT_ID` still defined in `SECRETS.example.h`
**File:** [SECRETS.example.h:43](file:///mnt/c/Users/aamer/OneDrive/Desktop/TECHNION/SEMESTER6/IOT/parkme_project/IOT_ParkMe/ESP32/SECRETS.example.h#L43)  
**Severity:** 🟠 Medium (Stale artifact)

```c++
constexpr uint32_t PARKME_GATE_SPOT_ID = 201;
```

After the refactor to `camera_mac`, `PARKME_GATE_SPOT_ID` is no longer referenced by any firmware code. However, it still exists in the example secrets file, which will confuse any developer who copies it to create a new `SECRETS.h`.

**Fix:** Remove the `PARKME_GATE_SPOT_ID` line from `SECRETS.example.h`.

---

### ✅ [RESOLVED] BUG-007: SSE client list is not cleaned up on disconnect
**File:** [main.py:598-605](file:///mnt/c/Users/aamer/OneDrive/Desktop/TECHNION/SEMESTER6/IOT/parkme_project/IOT_ParkMe/Backend/main.py#L598-L605)  
**Severity:** 🟠 Medium (Memory leak / stale broadcasts)

```python
async def event_generator():
    try:
        while True:
            message = await q.get()
            yield f"data: {message}\n\n"
    except asyncio.CancelledError:
        sse_clients.remove(client)
        raise
```

The cleanup only triggers on `asyncio.CancelledError`. If the client disconnects in a way that raises a different exception (e.g., `ConnectionResetError`, `GeneratorExit`), the client dict remains in `sse_clients` forever. Over time, `broadcast_event()` will push messages into abandoned queues that nobody reads, wasting memory.

**Fix:** Use a `finally` block instead of `except asyncio.CancelledError` to guarantee cleanup regardless of the disconnect reason.

---

### ✅ [RESOLVED] BUG-008: Frontend auto-login uses a potentially expired token
**File:** [app.js:358-361](file:///mnt/c/Users/aamer/OneDrive/Desktop/TECHNION/SEMESTER6/IOT/parkme_project/IOT_ParkMe/Frontend/app.js#L358-L361)  
**Severity:** 🟠 Medium (UX issue)

```javascript
if (localStorage.getItem('parkme_token')) {
    initDashboard();
}
```

Firebase ID tokens expire after 1 hour. If a user closes their browser and returns the next day, the stale token in `localStorage` will cause `initDashboard()` to fire, hit `GET /api/v1/users/me`, get a `401 Unauthorized`, and then silently fall back to the login screen. This works, but creates a visible flash of the dashboard screen before redirecting back to login.

**Fix:** Check the token's `exp` claim via `parseJwt()` before calling `initDashboard()`, or use Firebase's `onAuthStateChanged` listener for proper token refresh.

---

## 🟡 Low Severity / Documentation Issues

### ✅ [RESOLVED] BUG-009: Documentation still references old `mac_address` schema
**Files:**
- [firestore_database_structure.md](file:///mnt/c/Users/aamer/OneDrive/Desktop/TECHNION/SEMESTER6/IOT/parkme_project/IOT_ParkMe/Documentation/firestore_database_structure.md)
- [api_documentation.md](file:///mnt/c/Users/aamer/OneDrive/Desktop/TECHNION/SEMESTER6/IOT/parkme_project/IOT_ParkMe/docs/api_documentation.md)
- [esp32_hardware_spec.md](file:///mnt/c/Users/aamer/OneDrive/Desktop/TECHNION/SEMESTER6/IOT/parkme_project/IOT_ParkMe/docs/esp32_hardware_spec.md)
- [ESP32/README.md](file:///mnt/c/Users/aamer/OneDrive/Desktop/TECHNION/SEMESTER6/IOT/parkme_project/IOT_ParkMe/ESP32/README.md)

**Severity:** 🟡 Low (Documentation drift)

Multiple documentation files still reference the old single `mac_address` field and the old `spot_id` form field for the camera endpoint. Since the schema has been refactored to `sensor_mac` + `camera_mac`, these docs are now misleading.

Additionally, [ESP32/README.md:18](file:///mnt/c/Users/aamer/OneDrive/Desktop/TECHNION/SEMESTER6/IOT/parkme_project/IOT_ParkMe/ESP32/README.md#L18) says *"Set the correct spot_id values so they match the records in the backend database"*, which is no longer applicable since the camera now uses its MAC address.

**Fix:** Update all documentation files to reflect the `sensor_mac` / `camera_mac` schema.

---

### ✅ [RESOLVED] BUG-010: `seed_firestore.py` does not wipe `users` or `vehicles` collections
**File:** [seed_firestore.py:63-98](file:///mnt/c/Users/aamer/OneDrive/Desktop/TECHNION/SEMESTER6/IOT/parkme_project/IOT_ParkMe/Backend/seed_firestore.py#L63-L98)  
**Severity:** 🟡 Low (Incomplete cleanup)

The seeder wipes `parking_spots` and `parking_logs` before re-seeding, but it does **not** wipe `users` or `vehicles`. Because `seed_users` and `seed_vehicles` use `.set()` with explicit document IDs, re-runs are idempotent and won't create duplicates. However, if you manually added test users or vehicles via the Firebase Console, those extra documents will persist and never be cleaned up.

**Fix:** Add `delete_collection(db, "users")` and `delete_collection(db, "vehicles")` calls before their respective seed functions for full consistency.

---

### ✅ [RESOLVED] BUG-011: `GET /api/v1/logs` skips legitimate authorized parking events
**File:** [main.py:558-559](file:///mnt/c/Users/aamer/OneDrive/Desktop/TECHNION/SEMESTER6/IOT/parkme_project/IOT_ParkMe/Backend/main.py#L558-L559)  
**Severity:** 🟡 Low (Feature gap)

```python
        else:
            continue  # ← Skips all non-violation, non-special logs
```

The logs endpoint only returns violations, unidentified events, resolved events, and aborted events. Normal, successful parking events (authorized user parks in correct spot) are silently skipped. This means the admin has no way to view a complete historical timeline of all parking activity.

**Fix:** This may be intentional (the admin panel is a "Security Log", not a full audit trail), but it should be explicitly documented. If a full audit trail is desired, add a fifth message type for successful parks.

---

## Summary

| Severity | Count | IDs |
|----------|-------|-----|
| 🔴 Critical | 3 | BUG-001, BUG-002, BUG-003 |
| 🟠 Medium | 5 | BUG-004, BUG-005, BUG-006, BUG-007, BUG-008 |
| 🟡 Low | 3 | BUG-009, BUG-010, BUG-011 |
| **Total** | **11** | |
