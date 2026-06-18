# ParkMe — Logging & Edge Case Behavior

This document details the mechanics of the logging system, how various hardware edge cases are recorded, and how the frontend UI surfaces and allows resolution of these anomalies. It heavily cross-references [hardware_and_edge_cases.md](hardware_and_edge_cases.md).

---

## 1. Logging System Overview

### When and Why Events are Logged
The `parking_logs` Firestore collection serves as an append-only historical ledger for parking events. Logs are primarily created when:
- A vehicle arrives and is identified via the camera (`POST /api/v1/sensors/park`).
- An ultrasonic sensor detects a vehicle but no camera data arrives (Ghost Log creation via `POST /api/v1/sensors/heartbeat`).
- A node reconnects and flushes offline telemetry (`POST /api/v1/telemetry/bulk`).

*Note:* The Admin UI's `GET /api/v1/logs` endpoint acts strictly as a **Security Log**. By design, it filters out legitimate, authorized parking events and only returns anomalies (violations, unidentified vehicles, aborted parking, and admin resolutions).

### Log Structure / Fields
When a document is added to `parking_logs`, it typically contains:
*   `spot_id` (string): Logical spot identifier (e.g., `"A1"`).
*   `license_plate` (string): The detected plate string, or a system flag (`"UNIDENTIFIED"`, `"ABORTED"`, `"RESOLVED"`).
*   `entry_time` (timestamp): When the vehicle first arrived.
*   `exit_time` (timestamp | null): When the vehicle departed. `null` indicates the spot is currently occupied.
*   `is_violation` (boolean): `true` if unauthorized or unidentified, `false` otherwise.
*   `user_id` (string | null): The authenticated owner of the vehicle (if known).
*   `snapshot_role` (string | null): The user's RBAC role at the moment of entry.

---

## 2. Edge Case Behavior (Backend)

For a physical explanation of these edge cases, see [hardware_and_edge_cases.md](hardware_and_edge_cases.md).

### A. The "Ghost Log" (Hardware-Camera Asymmetry)
*   **What gets logged:** A new document is created with `license_plate = "UNIDENTIFIED"`, `is_violation = True`, and `user_id` / `snapshot_role` set to `null`.
*   **When:** The backend receives an ultrasonic heartbeat with `is_occupied = True`, but a query for an active log (where `exit_time == None`) for that spot returns empty.
*   **Why:** To ensure the system immediately flags a physical presence even if the camera is blocked, broken, or suffering a network outage.

### B. Ghost Log Self-Healing
*   **What gets logged:** No new document is created. Instead, the backend finds the active `"UNIDENTIFIED"` ghost log and **overwrites** it. The `license_plate` is updated to the actual OCR result, `user_id` and `snapshot_role` are populated, and `is_violation` is recalculated based on RBAC rules.
*   **When:** The camera node's `POST /api/v1/sensors/park` request finally arrives *after* the ultrasonic heartbeat has already created the ghost log.
*   **Why:** Camera retries or network stutter can delay the image payload. The system self-heals the log instead of creating duplicates.

### C. Bouncing Driver (Aborted Parking)
*   **What gets logged:** The active log for the spot is updated: `license_plate` is forced to `"ABORTED"`, `is_violation` is flipped to `False`, and `exit_time` is recorded.
*   **When:** The backend receives an `is_occupied = False` heartbeat, and calculates that the duration between `entry_time` and now is strictly `< 60` seconds.
*   **Why:** To avoid logging permanent violations for drivers who perform a three-point turn or immediately realize they parked in the wrong spot and leave.

### D. Duplicate LPR Deduplication
*   **What gets logged:** Nothing. The incoming request is dropped and no database writes occur.
*   **When:** The backend receives a `POST /api/v1/sensors/park` request for a license plate that already exists in the `cachetools.TTLCache` (which holds entries for a 120-second window).
*   **Why:** To gracefully handle bouncing gate ultrasonic triggers or rapid camera retry loops that submit the identical plate multiple times.

---

## 3. Frontend Behavior During Edge Cases

The UI reacts dynamically via Server-Sent Events (SSE) `/api/v1/stream` without requiring page reloads:

*   **Ghost Log ("UNIDENTIFIED"):** The UI receives a `spot_update` with `is_violation: true` and `license_plate: "UNIDENTIFIED"`. The parking spot card turns red, displays "UNIDENTIFIED" as the plate, and surfaces the "Resolve" button.
*   **Self-Healing:** The UI receives a subsequent `spot_update` overriding the previous state. The card dynamically drops the "UNIDENTIFIED" text, updates to the real plate, changes color based on actual authorization (e.g., green if valid), and the Resolve button instantly disappears.
*   **Bouncing Driver ("ABORTED"):** The UI receives a `spot_update` with `is_occupied: false`. The spot card turns green (empty state) and clears all plate/violation data. Simultaneously, a `log_event` pushes an info message to the activity stream stating the driver aborted parking.
*   **Duplicate LPR:** Since the backend drops these silently, no SSE events are broadcast. The frontend UI remains perfectly stable with no flickering or duplicate stream logs.

---

## 4. Resolve Button Lifecycle

The "Resolve" button exists in the Admin UI to handle permanent Ghost Logs (e.g., someone covered the license plate with mud, so the camera failed all retries).

### A. When it is Shown vs. Hidden
*   **Shown:** Strictly when a spot's `is_occupied` is `true` **AND** its `license_plate` exactly matches `"UNIDENTIFIED"`.
*   **Hidden:** At all other times. If the spot is empty, if the plate is known, if the state is `"ABORTED"`, or if it has already been `"RESOLVED"`, the button does not render.

### B. When it is Clickable vs. Disabled
To prevent an admin from manually resolving a spot while the camera is still legitimately attempting its 3 hardware retries, the button implements a strict cooldown:
*   **Disabled:** If the `last_seen` timestamp of the spot is less than 45 seconds old (the theoretical maximum duration of 3 camera network retries), the button renders with `opacity: 0.5` and `cursor: not-allowed`. A live javascript interval updates the text to `"Camera Retrying... (Xs)"` counting down every second.
*   **Clickable:** Once the 45-second `cooldown` elapsed, the javascript timeout fires, setting `disabled = false`, restoring opacity, and changing the text to `"Acknowledge & Resolve"`. Only then is the `onclick` event bound to the button.

### C. What Happens on Click
1.  **Backend Call:** The frontend fires a `PUT /api/v1/sensors/resolve` request with the `{ spot_id }` and the Admin's JWT authorization.
2.  **Backend State Change:** The backend queries `parking_logs` for the active `"UNIDENTIFIED"` log associated with that spot. It updates that specific log document, setting `is_violation: False` and `license_plate: "RESOLVED"`.
3.  **SSE Broadcast:** The backend fires two SSE events:
    *   A `spot_update` pushing `license_plate: "RESOLVED"` and `is_violation: False`.
    *   A `log_event` of type `info` stating `Admin <Name> resolved anomaly at spot <spot_id>.`
4.  **Immediate UI Side Effect:** The UI toast system displays `"Spot <spot_id> resolved successfully."` Because of the SSE broadcast, the spot card locally drops its red violation styling, replacing the text with "RESOLVED", and the Resolve button hides itself. *(Note: The current `app.js` also contains demo fallback logic to physically remove the DOM card if the backend call fails, but in production, the SSE stream drives the state).*
