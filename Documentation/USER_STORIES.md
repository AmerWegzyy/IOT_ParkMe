# ParkMe User Stories and Acceptance Criteria

## 1. Purpose

This document is the requirements source for auditing the ParkMe codebase.

The audit must compare the current implementation against every numbered user story and the additional requirements stated in the project definition. A feature is not considered complete merely because a function, endpoint, screen, or database field exists. The complete user flow must work across the relevant components.

Project: **ParkMe – Group #12**

System summary: An IoT smart-parking system for the Technion campus. ESP32-based parking nodes detect occupancy, an ESP32-CAM captures license plates, a FastAPI backend performs LPR/OCR and authorization, Firestore stores system state, and a web interface displays parking and administration information.

## 2. Actors

### Standard User

A student, lecturer, staff member, or special-needs driver who can:

- Sign in to the web application.
- View parking availability allowed for their permit or role.
- Receive a parking-spot recommendation.
- See whether access was approved or denied.
- Potentially earn incentive points.

### Lecturer

A standard user whose plate should grant access to lecturer parking when correctly registered.

### Special-needs Driver

A standard user who should be directed to accessible parking and should not be sent to unauthorized categories.

### Administrator

Technion security or maintenance personnel who can:

- View all parking spots.
- Review violations and unreadable plates.
- View sensor health and battery information.
- View logs and statistics.
- Configure parking nodes and categories.
- Receive fault, offline, low-battery, and violation alerts.

### Technician

A person who installs a sensor and calibrates it for the physical parking spot.

## 3. Audit Status Definitions

Use exactly one primary status for each requirement:

- **DONE** — The complete user flow is implemented, integrated, and supported by convincing tests or runtime evidence.
- **PARTIAL** — Important parts exist, but acceptance criteria, integration, error handling, UI, persistence, or tests are incomplete.
- **MISSING** — No meaningful implementation was found.
- **BROKEN** — Code exists, but it cannot work correctly in the current version.
- **NOT TESTABLE** — The implementation appears present, but required hardware, credentials, cloud services, or runtime access prevented verification.

A story must not be marked DONE based only on documentation or comments.

---

# 4. Numbered User Stories

## US-01 — Real-time Parking Availability

**As a:** Standard User  
**I want:** To see real-time parking availability.  
**So that:** I do not waste time driving in circles during peak hours.

### Acceptance criteria

1. Every configured parking spot has a stable unique identifier.
2. The ultrasonic sensor distinguishes at least FREE, OCCUPIED, and invalid/unknown readings.
3. Noisy or invalid readings do not immediately create false state changes.
4. State changes reach the backend with a timestamp and sensor identity.
5. The database stores the latest state and last-seen time.
6. The web application updates without a full manual refresh.
7. A user sees only the parking categories allowed for that role.
8. An offline or stale sensor is not presented as confidently FREE.
9. Multiple spots and sensor nodes are supported.
10. Reconnection does not leave the dashboard permanently stale.

### Evidence to inspect

- Sensor distance sampling and classification.
- Telemetry/heartbeat delivery and retry behavior.
- Firestore spot updates.
- SSE or polling behavior.
- Frontend stale/offline logic.
- Role-based filtering.
- Automated tests for state transitions and stale data.

---

## US-02 — License Plate Recognition Access

**As a:** Lecturer  
**I want:** The system to automatically recognize my license plate.  
**So that:** I can park in my high-priority zone without manual verification.

### Acceptance criteria

1. Occupancy triggers a fresh camera capture for the current parking cycle.
2. The image is sent to the correct backend endpoint with the camera/spot identity.
3. OCR uses the configured real recognition service, not a hardcoded mock in production.
4. Plate normalization accepts plausible Israeli 7- or 8-digit plates.
5. OCR noise from stickers, phone numbers, or unrelated text is not merged into a false plate.
6. The plate is mapped to a registered vehicle and user.
7. The user role is compared with the parking category on the server.
8. Correctly authorized users receive WELCOME.
9. Unregistered, mismatched, or unreadable plates fail safely.
10. Unreadable plates enter the administrator review flow.
11. Repeated camera messages do not create duplicate active sessions.
12. Tests include clean images, noisy OCR text, unreadable images, and incorrect recognition.

### Evidence to inspect

- ESP32-CAM capture and retry logic.
- Google Vision integration.
- Plate extraction and validation helpers.
- Vehicle/user Firestore lookup.
- Authorization decision.
- OCR unit tests and image-pipeline results.

---

## US-03 — Violation Alert

**As an:** Administrator  
**I want:** To receive a notification when an unauthorized car is detected.  
**So that:** I can enforce parking regulations instantly and efficiently.

### Acceptance criteria

1. Unauthorized access is detected for both unregistered plates and role/category mismatch.
2. A violation record includes spot, time, plate/result, and decision reason.
3. Evidence images are retained when appropriate.
4. The administrator receives a real-time visible alert.
5. The alert is not silently lost if the admin changes screens.
6. Duplicate camera uploads do not create duplicate alerts.
7. The administrator can distinguish unresolved, accepted, rejected, and cleared cases.
8. Alert failures are logged.
9. Access is restricted to administrators.

### Evidence to inspect

- Violation decision code.
- Firestore parking logs.
- SSE/admin frontend notification behavior.
- Manual Accept/Reject flow.
- Evidence image handling.
- Alert acknowledgement or resolution state.

---

## US-04 — Accessible Parking

**As a:** Special-needs Driver  
**I want:** To be directed to restricted accessible parking zones.  
**So that:** I can easily find a suitable parking spot without checking unauthorized zones.

### Acceptance criteria

1. Accessible spots have a valid, consistent category.
2. The authenticated special-needs user is recognized by role or accessibility entitlement.
3. The user sees accessible spots without seeing unauthorized alternatives as recommendations.
4. Recommendations exclude occupied, stale, offline, and invalid spots.
5. The backend also enforces authorization; the rule is not frontend-only.
6. The UI clearly reports when no accessible spot is available.
7. Tests cover accessible authorization and non-accessible denial.

### Evidence to inspect

- User role model.
- Spot category model.
- Backend authorization.
- Frontend filtering and recommendation.
- Empty-state messaging.

---

## US-05 — Sensor Battery and Maintenance Monitoring

**As an:** Administrator  
**I want:** To monitor the real-time battery life of every sensor node.  
**So that:** I can replace batteries before a sensor goes offline.

### Acceptance criteria

1. Each sensor reports a battery value linked to its identity.
2. Battery conversion is bounded and handles invalid measurements.
3. The backend stores the latest battery value and timestamp.
4. The admin dashboard shows battery per sensor or spot.
5. A configurable low-battery threshold exists.
6. Low battery produces a clear warning or alert.
7. Stale battery values are distinguishable from fresh values.
8. The system does not show a disconnected sensor as healthy.
9. Tests cover empty, full, below-threshold, invalid, and missing readings.

### Evidence to inspect

- ESP32 voltage conversion.
- Heartbeat payload.
- Firestore fields.
- Admin battery UI.
- Low-battery threshold and alert logic.
- Maintenance history or acknowledgement.

---

## US-06 — Display Access Status on the Device

**As a:** Standard User  
**I want:** The IoT device screen to clearly display either a Welcome message or an Access Denied notification when I attempt to enter.  
**So that:** I receive immediate visual confirmation of my authorization status without confusion.

### Acceptance criteria

1. A local display is associated with the correct spot.
2. The backend sends a WELCOME or DENIED result to the correct display.
3. The screen renders the result clearly for a suitable duration.
4. Scanning, camera failure, manual review, and offline states have understandable messages.
5. A stale message from the previous vehicle is cleared.
6. Local camera status cannot permanently overwrite the final server decision.
7. Display delivery has an acknowledgement or fallback mechanism.
8. Tests or hardware evidence verify both WELCOME and DENIED.

### Evidence to inspect

- OLED driver and display state machine.
- Backend display command queue.
- SSE and poll fallback.
- Display result/ack endpoint.
- Hardware test sketches.

---

## US-07 — Logs and Statistics

**As an:** Administrator  
**I want:** To view parking usage logs over time.  
**So that:** I can see patterns, identify peak hours, and manage utilization.

### Acceptance criteria

1. Entry and exit times are recorded.
2. Logs identify spot, user/plate when permitted, authorization outcome, and violation state.
3. Active and completed sessions are distinguishable.
4. The admin can view historical logs.
5. Statistics include at least occupancy/session counts and peak-use information.
6. Date-range filtering or another bounded query prevents an unbounded full-history scan.
7. Pagination or a result limit exists.
8. Time zones are handled consistently.
9. Retention and evidence-image behavior are documented.
10. Only administrators can access sensitive logs and statistics.
11. Tests verify aggregation and important edge cases.

### Evidence to inspect

- `parking_logs` writes.
- Exit/close logic.
- Logs and usage-stat endpoints.
- Frontend statistics section.
- Query limits, indexes, date filters, and tests.

---

## US-08 — Sensor-node Configuration

**As an:** Administrator  
**I want:** To configure each sensor node to represent a specific parking category such as Student, Lecturer, Staff, or Accessible.  
**So that:** The system enforces the correct authorization rules for that specific spot.

### Acceptance criteria

1. An administrator can configure a spot without editing source code.
2. The configuration includes spot ID, sensor identity, camera identity, display identity, and category as applicable.
3. Only allowed category values are accepted.
4. Duplicate MAC addresses and duplicate mappings are rejected.
5. Changes persist in Firestore.
6. The new configuration is reflected by the backend and frontend.
7. Authorization uses the updated category.
8. Invalid or incomplete configurations produce clear errors.
9. Only administrators can change configuration.
10. Tests cover valid updates, invalid categories, duplicates, and unauthorized callers.

### Evidence to inspect

- Admin API endpoints.
- Admin configuration UI.
- Firestore validation.
- Seed scripts versus runtime configuration.
- Authorization after configuration changes.

---

## US-09 — Offline and Failure Handling

**As an:** Administrator  
**I want:** To receive an error notification if a sensor disconnects from Wi-Fi or loses power.  
**So that:** The system does not display incorrect parking availability.

### Acceptance criteria

1. Every sensor sends a last-seen timestamp or heartbeat.
2. The backend computes stale/offline status, not only the browser.
3. Offline spots are represented as UNKNOWN/OFFLINE rather than FREE.
4. Administrators receive a clear offline warning.
5. Reconnection clears the warning.
6. The sensor retries failed telemetry.
7. Important state is preserved during temporary disconnection.
8. Replayed data does not create incorrect event ordering.
9. Camera, OCR, database, SSE, and display failures are logged and handled.
10. Tests cover timeout, reconnect, duplicate replay, and out-of-order events.

### Evidence to inspect

- Wi-Fi reconnect code.
- NVS/offline telemetry queue.
- Bulk replay endpoint and whether firmware calls it.
- Backend stale-state computation.
- Frontend offline warning.
- Cloud logging and error handling.

---

## US-10 — Graphical User Interface

**As a:** Standard User  
**I want:** To use a dedicated web application interface.  
**So that:** I can easily interact with the system and check parking while on the go.

### Acceptance criteria

1. Firebase login works and expired sessions are handled.
2. The backend verifies authentication and role.
3. The dashboard is usable for standard users and administrators.
4. Availability updates in near real time.
5. Loading, empty, disconnected, and API-error states are visible.
6. The interface is usable on a phone-sized screen.
7. Sensitive admin information is hidden from non-admin users.
8. User-generated or OCR-derived content is rendered safely.
9. Network reconnect does not duplicate listeners or corrupt state.
10. Basic frontend tests or an explicit manual test checklist exists.

### Evidence to inspect

- `Frontend/index.html`, `app.js`, and `style.css`.
- Authentication and token handling.
- Role-based views.
- SSE reconnect and polling.
- Responsive CSS.
- DOM rendering safety.
- Error and empty states.

---

## US-11 — Calibration / Setup Mode

**As a:** Technician  
**I want:** To calibrate the baseline distance of the ultrasonic sensor during installation.  
**So that:** The system accurately detects a car regardless of the parking spot's physical dimensions.

### Acceptance criteria

1. Calibration can be triggered in the field without reflashing firmware.
2. The technician receives clear start, success, and failure feedback.
3. Multiple samples are used and invalid readings are rejected.
4. The saved calibration is specific to the sensor node.
5. The calibration survives reboot.
6. The saved baseline is actually used to calculate the occupied threshold.
7. The calculated threshold is actually used by occupancy classification.
8. A safe fallback exists when no valid calibration is stored.
9. Extreme or impossible measurements are rejected or bounded.
10. Recalibration replaces the previous value safely.
11. Tests or hardware evidence verify persistence and changed detection behavior.

### Evidence to inspect

- Calibration button handling.
- Baseline sampling.
- NVS/Preferences persistence.
- Threshold calculation.
- Occupancy classification call site.
- OLED/serial feedback.
- Compile-time, unit, or hardware tests.

---

# 5. Additional Requirements Found in the Project Definition

These requirements are mentioned in the actor description even though they are not numbered in the original table. They must be audited separately.

## R-01 — Parking-spot Recommendation

**As a:** Standard User  
**I want:** To receive a suitable parking-spot recommendation.  
**So that:** I can go directly to a usable spot.

### Acceptance criteria

1. Recommendations respect the user's role and accessibility entitlement.
2. Occupied, offline, stale, or invalid spots are excluded.
3. The selection rule is documented and deterministic.
4. The UI handles the case where no suitable spot exists.
5. Recommendation logic is tested.
6. The recommendation cannot bypass backend authorization.

---

## R-02 — Incentive Points

**As a:** Standard User  
**I want:** To earn incentive points for desired parking behavior.  
**So that:** I am encouraged to use parking resources responsibly.

### Acceptance criteria

1. The behaviors that award or remove points are explicitly defined.
2. Points are stored per user.
3. Awards are idempotent and cannot be duplicated by repeated events.
4. Users can view their points.
5. Administrators can audit point transactions.
6. Permissions prevent users from directly changing their balances.
7. Tests cover earning, duplicate events, reversal, and unauthorized changes.

---

# 6. Cross-cutting Quality Requirements

The audit must also report these issues even when they do not map to only one story:

1. **Testing:** unit, integration, frontend, cloud, and hardware-in-the-loop coverage.
2. **Security:** hardware endpoint authentication, Firebase authorization, CORS, secret handling, TLS verification, input validation, and evidence-image privacy.
3. **Reliability:** Cloud Run instance behavior, in-memory queues/SSE state, retries, idempotency, race conditions, and Firestore failures.
4. **Performance and cost:** unbounded Firestore scans, large base64 images, repeated polling, and Vision API usage.
5. **Maintainability:** very large files, dead code, duplicated constants, stale tests, and conflicting documentation.
6. **Observability:** structured logs, error metrics, sensor health, alert delivery, and traceability by request/spot.
7. **Data integrity:** valid role/category enums, unique hardware mappings, timestamps, session lifecycle, and migration/seed safety.
8. **Deployment:** Cloud Run, Firebase Hosting, ADC/service account use, environment configuration, health checks, and rollback instructions.

---

# 7. Required Audit Result Table

The final audit should include this table with one row per requirement:

| ID | Requirement | Status | Code evidence | Test/runtime evidence | Missing acceptance criteria | Risk | Recommended next action |
|---|---|---|---|---|---|---|---|
| US-01 | Real-time availability |  |  |  |  |  |  |
| US-02 | LPR access |  |  |  |  |  |  |
| US-03 | Violation alert |  |  |  |  |  |  |
| US-04 | Accessible parking |  |  |  |  |  |  |
| US-05 | Battery and maintenance |  |  |  |  |  |  |
| US-06 | Device access display |  |  |  |  |  |  |
| US-07 | Logs and statistics |  |  |  |  |  |  |
| US-08 | Node configuration |  |  |  |  |  |  |
| US-09 | Offline handling |  |  |  |  |  |  |
| US-10 | Web GUI |  |  |  |  |  |  |
| US-11 | Calibration/setup |  |  |  |  |  |  |
| R-01 | Spot recommendation |  |  |  |  |  |  |
| R-02 | Incentive points |  |  |  |  |  |  |
