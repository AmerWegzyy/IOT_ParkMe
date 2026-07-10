# ParkMe Project Audit Instructions for Claude Code

## Purpose

You are reviewing the **ParkMe – Group #12** repository.

ParkMe is an IoT smart-parking system for the Technion campus. It should:

- Detect real-time parking-space availability using ultrasonic sensors.
- Recognize vehicle license plates using LPR.
- Enforce role-based parking permissions for Students, Lecturers, Staff, and special-needs drivers.
- Display parking information through a web application.
- Notify administrators about violations, disconnected devices, power loss, and low battery.
- Store logs and statistics.
- Allow configuration and calibration of sensor nodes.

Your task is to inspect the entire repository and determine how completely and correctly it implements this project definition.

---

# Main Instructions

1. Read the entire repository before reaching conclusions.
2. Identify the project architecture automatically:
   - ESP32 or ESP32-CAM firmware
   - Backend/API
   - Database or cloud service
   - Frontend/web application
   - LPR or computer-vision service
   - Configuration files
   - Tests
   - Deployment files
   - Documentation
3. Do **not** assume a feature exists because a file, function, class, endpoint, UI page, or comment has the correct name.
4. Mark a feature as implemented only when you can cite concrete evidence from the repository.
5. Run relevant safe checks and tests when possible.
6. Do not connect to real production systems, use real credentials, flash hardware, delete data, or make destructive changes.
7. Do not modify the project during the initial audit.
8. If hardware is unavailable, perform static analysis and clearly state what still requires physical testing.
9. If an external service, camera, sensor, database, or API is mocked, distinguish the mock implementation from real integration.
10. Never claim that a requirement passes when the repository contains only a placeholder, TODO, hard-coded demo, or incomplete stub.

---

# Required Deliverable

Create a file named:

`PROJECT_AUDIT_REPORT.md`

The report must contain:

1. Executive summary
2. Detected architecture
3. Build and test results
4. Requirement traceability matrix
5. Detailed findings for every user story
6. Security and privacy findings
7. Reliability and offline-behavior findings
8. Hardware and firmware findings
9. Frontend, backend, database, and LPR findings
10. Missing or incomplete requirements
11. Prioritized fix plan
12. Final readiness score

Do not replace this instruction file.

---

# Evidence Rules

For every conclusion, provide evidence in this format:

- **Status:** Complete / Partial / Missing / Cannot Verify / Broken
- **Evidence:** file path and line range, function/class/endpoint/component name, test name, or command output
- **Explanation:** why the evidence satisfies or fails the requirement
- **Risk:** Critical / High / Medium / Low
- **Recommended action:** exact next step

Example:

```text
Status: Partial
Evidence:
- firmware/src/parking_sensor.cpp:42-97, function updateOccupancy()
- backend/routes/spaces.py:18-54, endpoint GET /api/spaces
Explanation:
The sensor publishes occupancy updates and the backend exposes them, but stale readings are not marked unavailable.
Risk: High
Recommended action:
Store last_seen for every node and mark the space status unknown after a defined timeout.
```

Do not cite only a directory name. Use the most precise evidence available.

---

# Status Definitions

Use these definitions consistently:

- **Complete:** Fully implemented, integrated, and supported by meaningful evidence or tests.
- **Partial:** Some required behavior exists, but important behavior, integration, validation, or testing is missing.
- **Missing:** No meaningful implementation was found.
- **Cannot Verify:** Implementation may exist, but verification requires unavailable hardware, credentials, external services, or data.
- **Broken:** The implementation exists but fails to build, run, integrate, or meet the stated behavior.

---

# Phase 1 – Repository Discovery

Inspect at least the following when they exist:

- `README*`
- `CLAUDE.md`
- Source directories
- Firmware sketches and PlatformIO/Arduino configuration
- `package.json`
- `requirements.txt`
- `pyproject.toml`
- `Pipfile`
- `Dockerfile*`
- `docker-compose*`
- Database schemas and migrations
- Environment examples
- API routes
- Authentication and authorization code
- Frontend routes and components
- LPR model/configuration files
- Unit, integration, and end-to-end tests
- CI workflows
- Deployment configuration
- Documentation and diagrams

Create an architecture summary that explains:

1. Main components
2. Communication protocol between components
3. Data flow from sensor to user interface
4. Data flow from camera/LPR to authorization decision
5. Database entities
6. Authentication and role model
7. External services
8. Hardware dependencies
9. How the system is started locally
10. How it is intended to be deployed

Flag undocumented components and contradictions between documentation and code.

---

# Phase 2 – Build and Automated Checks

Determine the correct commands from the repository instead of guessing.

Run safe commands that apply to the detected stack, such as:

- Dependency installation validation
- Compilation or build
- Type checking
- Unit tests
- Integration tests
- Linting
- Static analysis
- Frontend production build
- Firmware compilation
- Database migration validation

Record:

- Every command executed
- Whether it passed
- Important output
- Failed tests
- Warnings that could affect correctness
- Checks that could not run and why

Do not hide failures.

If dependencies cannot be installed because internet access or credentials are unavailable, continue with static analysis.

---

# Phase 3 – Requirement Traceability Matrix

Create a table with one row for each user story:

| ID | User story | Status | Main evidence | Tests | Main gap | Risk |
|---|---|---|---|---|---|---|

Use the story names below as the source of truth.

---

# User Story 1 – Real-Time Availability

## Requirement

A standard user can view current parking-space availability and avoid driving around searching for a space.

## Check

- Ultrasonic sensor logic detects occupied versus free.
- Measurements are filtered or stabilized to reduce false changes.
- Sensor readings reach the backend/cloud.
- Every parking space has a current status.
- The API returns availability.
- The web interface displays availability.
- Availability is updated without requiring a full application restart.
- The system records a timestamp or `last_seen`.
- Stale sensor data is not displayed as trustworthy real-time data.
- Errors or unknown status are distinguishable from occupied status.
- Multiple parking spaces or nodes are supported.
- Availability is filtered by the user's permitted parking category when required.

## Suggested acceptance tests

- Free space becomes occupied after a valid sensor reading.
- Occupied space becomes free after a valid sensor reading.
- Noisy measurements do not rapidly toggle status.
- Missing updates cause the space to become `unknown` or `offline`.
- Two different sensor nodes update two different parking spaces.
- The frontend reflects an API update correctly.

---

# User Story 2 – LPR Access

## Requirement

The system automatically recognizes a lecturer's license plate and allows access to the lecturer's permitted high-priority zone.

## Check

- Image capture exists for ESP32-CAM or another camera source.
- Images are transferred safely to an LPR component.
- Plate detection and OCR/recognition are implemented or integrated.
- Plate text is normalized consistently.
- Confidence or recognition failure is handled.
- The recognized plate is matched against registered vehicles.
- Vehicle owner role or permit is retrieved.
- Access is evaluated for the requested parking zone.
- Authorized and unauthorized outcomes are clearly returned.
- The system avoids granting access on an LPR failure.
- Duplicate, malformed, or spoofed inputs are handled.
- Real LPR integration is distinguished from a hard-coded plate or mock result.

## Suggested acceptance tests

- Registered lecturer plate in lecturer zone → authorized.
- Registered student plate in lecturer-only zone → denied.
- Unknown plate → denied or sent for manual review.
- Low-confidence recognition → not automatically authorized.
- Plate with spaces/dashes/case differences is normalized correctly.
- Camera or LPR service failure produces a safe result.

---

# User Story 3 – Parking Violation Alert

## Requirement

An administrator receives a notification when an unauthorized vehicle is detected.

## Check

- Unauthorized parking or entry is detected.
- A violation record is created.
- The violation includes useful context:
  - plate number when available
  - parking space or zone
  - timestamp
  - reason
  - image/reference when legally and technically appropriate
- A notification channel exists, such as dashboard alert, email, push notification, or another documented mechanism.
- Duplicate events are rate-limited or deduplicated.
- Administrators can distinguish new, acknowledged, and resolved violations.
- Ordinary users cannot access administrator alerts.
- Failure to send an alert is logged or retried.

## Suggested acceptance tests

- Unauthorized role in restricted zone creates one violation.
- Repeated identical sensor/LPR events do not create excessive duplicate alerts.
- Administrator can retrieve the violation.
- Standard user cannot retrieve administrator violations.
- Notification-service failure is handled without losing the violation record.

---

# User Story 4 – Accessible Parking

## Requirement

A special-needs driver is directed only to suitable accessible parking and is not directed to unauthorized zones.

## Check

- Accessible parking is represented as a distinct category.
- User or vehicle permits can include accessible authorization.
- Recommendation logic prioritizes valid accessible spaces.
- Non-authorized users cannot receive or use accessible-space authorization.
- An accessible driver is not directed to a zone outside their permissions.
- No-space-available behavior is clear and safe.
- The user interface clearly labels accessible spaces without exposing sensitive personal details.

## Suggested acceptance tests

- Authorized accessible driver receives a free accessible-space recommendation.
- Standard student is not authorized for accessible-only parking.
- No accessible space available returns a clear result.
- Offline accessible sensor is not recommended as certainly free.

---

# User Story 5 – Battery and Sensor Maintenance

## Requirement

An administrator can monitor the real-time battery level of every sensor node and replace batteries before a node goes offline.

## Check

- Battery voltage is sampled using a voltage divider or supported sensor.
- Raw ADC readings are converted to meaningful voltage or percentage.
- Calibration constants are not unexplained magic numbers.
- Battery level is transmitted with a node identifier and timestamp.
- Backend stores the latest battery state.
- Administrator dashboard displays battery state for every node.
- Low-battery threshold exists.
- Low-battery alerts are rate-limited.
- Impossible readings are rejected or flagged.
- Battery readings are not presented as real-time after the node becomes stale.

## Suggested acceptance tests

- Valid reading maps to an expected voltage/percentage.
- Low battery creates an administrator warning.
- Normal battery does not create a warning.
- Invalid ADC value is rejected or marked invalid.
- Every configured sensor node appears in maintenance status.

---

# User Story 6 – Device Access Display

## Requirement

The IoT device screen displays a clear **Welcome** message for authorized access or **Access Denied** for unauthorized access.

## Check

- A physical display component is implemented or documented.
- Display initialization and error handling exist.
- Authorization result reaches the display logic.
- Exact authorized and denied states are distinguishable.
- Messages are visible for a suitable duration.
- Previous messages are cleared or replaced correctly.
- Unknown/error state does not incorrectly show Welcome.
- Display behavior is non-blocking or does not break sensing/network logic.

## Suggested acceptance tests

- Authorized decision displays `Welcome`.
- Unauthorized decision displays `Access Denied`.
- Network/LPR error does not display `Welcome`.
- Consecutive decisions update the screen correctly.

---

# User Story 7 – Logs and Statistics

## Requirement

An administrator can view parking usage logs over time, identify patterns and peak hours, and manage utilization.

## Check

- Occupancy changes are stored historically, not only as current state.
- Important events contain timestamps.
- Time zones are handled consistently.
- Logs can be queried by parking space, zone, category, and date range.
- Statistics are calculated from actual stored events.
- Peak-hour or utilization information exists.
- The administrator interface presents logs or charts/tables.
- Pagination or limits exist for large histories.
- Ordinary users cannot access restricted operational logs.
- Data retention is documented or configurable.

## Suggested acceptance tests

- Occupancy events produce historical records.
- Date-range query returns only matching records.
- Peak-hour calculation is reproducible from stored data.
- Empty data set is handled.
- Unauthorized user cannot access administrator statistics.

---

# User Story 8 – Sensor-Node Configuration

## Requirement

An administrator can configure every sensor node to represent a specific parking category: Student, Lecturer, Staff, or Accessible.

## Check

- Sensor nodes have unique persistent identifiers.
- A node can be mapped to a parking space.
- Each parking space has a validated category.
- Allowed category values are constrained.
- Administrator-only configuration endpoint or interface exists.
- Configuration survives restart.
- Invalid or duplicate node mappings are handled.
- Changing category affects authorization and availability filtering.
- Firmware configuration and server configuration cannot silently conflict.
- Configuration changes are logged when appropriate.

## Suggested acceptance tests

- Administrator maps node to Lecturer category.
- Standard user cannot change node configuration.
- Invalid category is rejected.
- Configuration persists after backend restart.
- Category change affects access-control results.

---

# User Story 9 – Offline and Failure Handling

## Requirement

An administrator receives an error notification when a sensor disconnects from Wi-Fi or loses power, and users are not shown incorrect availability.

## Check

- Firmware handles Wi-Fi disconnection.
- Reconnection uses bounded retry/backoff rather than a tight blocking loop.
- Local caching or queued updates are handled safely, when implemented.
- Backend tracks heartbeat or `last_seen`.
- Node-offline timeout is defined.
- Offline spaces become `unknown` or unavailable for recommendation.
- Administrator receives an offline alert.
- Recovery generates an online/recovered state.
- Duplicate alerts are controlled.
- Power loss is inferred through missed heartbeat or another documented mechanism.
- Cached events have timestamps so outdated states do not overwrite newer states.
- The system does not claim it can directly notify after complete power loss unless another component detects the missing heartbeat.

## Suggested acceptance tests

- Stop node updates → backend marks node offline after timeout.
- Offline space is not shown as definitely free.
- Administrator receives one offline alert.
- Resume updates → node becomes online.
- Old cached event does not overwrite a newer state.
- Temporary Wi-Fi loss does not crash firmware.

---

# User Story 10 – Web GUI

## Requirement

A standard user can use a dedicated web application to interact with the system and check parking while on the go.

## Check

- The application has a usable frontend.
- Availability view is connected to real backend data.
- Loading, empty, offline, and error states are shown.
- Mobile-responsive behavior exists.
- User role and permitted categories affect what is displayed.
- Spot recommendations are visible when implemented.
- Authentication flow works when required.
- Administrator functions are separated and protected.
- The GUI does not expose secrets, internal credentials, or unrestricted admin APIs.
- Basic accessibility is considered:
  - labels
  - keyboard usage
  - readable status indicators
  - status not communicated only through color

## Suggested acceptance tests

- Frontend production build succeeds.
- Availability data is rendered from API response.
- API failure shows an error state.
- Mobile viewport remains usable.
- Standard user cannot open protected administrator functionality.

---

# User Story 11 – Calibration and Setup Mode

## Requirement

A technician can calibrate the ultrasonic sensor's baseline distance during installation so that vehicle detection works with different parking-space dimensions.

## Check

- Calibration mode can be entered intentionally.
- Baseline distance is measured using multiple samples where appropriate.
- Invalid readings and timeouts are handled.
- Calibration result is stored persistently.
- Occupancy threshold is derived from calibration or configurable parameters.
- Calibration does not accidentally run during normal operation.
- A technician receives success/failure feedback.
- Recalibration is supported.
- Different nodes can store different calibration values.
- Firmware restart preserves calibration.

## Suggested acceptance tests

- Calibrate using valid readings and store baseline.
- Restart firmware and recover stored baseline.
- Invalid/no-echo readings fail safely.
- Two nodes can use different baseline values.
- Normal sensing uses the calibrated value.

---

# Additional Functional Requirement – Spot Recommendations

The project description says standard users can receive parking-spot recommendations.

Check whether:

- A recommendation algorithm or endpoint exists.
- It considers availability.
- It considers the user's role/permit.
- It considers accessible authorization.
- It excludes offline or stale spaces.
- It avoids recommending occupied spaces.
- Selection criteria are documented, such as distance, priority, or first available.
- No-match behavior is clear.

Mark this separately even if it overlaps with stories 1 and 4.

---

# Additional Functional Requirement – Incentive Points

The project description says standard users can earn incentive points.

Check whether:

- A points model exists.
- Earning rules are defined.
- Points are associated with authenticated users.
- Duplicate events cannot award points repeatedly.
- Users can view their points.
- Administrators cannot arbitrarily modify points without authorization and validation.
- Abuse prevention exists.
- Tests cover point awards and duplicate prevention.

If no implementation exists, mark this requirement missing even though it has no numbered user story.

---

# Role-Based Authorization Matrix

Determine the actual behavior in code and compare it with this expected conceptual model:

| Role/permit | Student zone | Lecturer zone | Staff zone | Accessible zone |
|---|---:|---:|---:|---:|
| Student | Expected according to permit | Denied unless explicitly allowed | Denied unless explicitly allowed | Denied without accessible permit |
| Lecturer | According to configured policy | Allowed | According to configured policy | Denied without accessible permit |
| Staff | According to configured policy | According to configured policy | Allowed | Denied without accessible permit |
| Accessible permit | Only where base role permits | Only where base role permits | Only where base role permits | Allowed |

Do not invent a policy when the repository does not define one. Report ambiguity as a requirements gap.

Check authorization at the backend or trusted control layer. Hiding a button in the frontend is not sufficient authorization.

---

# Data Model Review

Identify and review entities such as:

- User
- Role
- Permit
- Vehicle
- License plate
- Parking lot
- Parking zone
- Parking space
- Sensor node
- Sensor reading
- Current occupancy
- Battery reading
- Calibration
- Access attempt
- Violation
- Notification
- Historical parking event
- Incentive-points transaction

Check:

- Primary and foreign keys
- Unique constraints
- Required fields
- Valid enum/category constraints
- Timestamps
- Indexes for common queries
- Cascading delete behavior
- Duplicate-event prevention
- Migration consistency
- Whether current state and history are modeled separately
- Whether every sensor reading is linked to the correct node and parking space

---

# API Review

List every discovered endpoint with:

| Method | Path | Purpose | Authentication | Allowed roles | Input validation | Main response |
|---|---|---|---|---|---|---|

Check:

- Authentication
- Authorization
- Input validation
- Error codes
- Pagination
- Rate limiting where appropriate
- CORS configuration
- Secrets handling
- File upload limits for images
- Protection against path traversal and unsafe file names
- Database error handling
- Consistent response formats
- OpenAPI or API documentation accuracy

Perform safe request-level tests when the project can run locally.

---

# LPR and Image-Processing Review

Review the full pipeline:

1. Image capture
2. Image transmission
3. Plate detection
4. Character recognition
5. Normalization
6. Confidence evaluation
7. Vehicle lookup
8. Role/permit lookup
9. Zone authorization
10. Decision, logging, notification, and display response

Check:

- Whether recognition is real, mocked, or hard-coded
- Supported plate formats
- Confidence threshold
- False-positive safety
- Failure behavior
- Image size/type validation
- Temporary file cleanup
- Model availability
- CPU/memory assumptions
- Timeout handling
- Privacy and retention
- Whether stored images are necessary
- Whether tests use representative sample images without exposing personal data

A recognized string alone does not prove a complete LPR access feature.

---

# Firmware and Hardware Review

## Expected hardware

1. ESP32 microcontroller
2. HC-SR04 ultrasonic sensor
3. ESP32-CAM module
4. Li-ion battery
5. Voltage divider or battery-voltage sensor
6. A device display for Welcome/Access Denied, because user story 6 requires one

Check whether the documentation and code agree on:

- Pin assignments
- Voltage compatibility
- Power requirements
- Ground connections
- HC-SR04 echo voltage protection for ESP32
- ESP32-CAM pins and memory limitations
- Battery measurement range
- ADC conversion
- Display model and communication interface
- Deep sleep or power-saving strategy
- Wi-Fi credentials provisioning
- Unique device identity
- Firmware update strategy
- Watchdog or recovery behavior

Do not treat a hardware requirement as verified only from source code. Mark physical wiring and real sensor behavior as `Cannot Verify` until supported by test evidence.

---

# Reliability Review

Check for:

- Blocking loops
- Unbounded retries
- Missing timeouts
- Memory leaks
- Resource cleanup
- Race conditions
- Duplicate MQTT/HTTP events
- Out-of-order readings
- Clock/time-zone errors
- Stale data
- Backend restart recovery
- Database reconnect behavior
- Frontend reconnect behavior
- Sensor reboot behavior
- Idempotent event processing
- Logging without sensitive data
- Reasonable error messages

Trace at least these failure scenarios:

1. Sensor has power but no Wi-Fi.
2. Sensor loses power.
3. Backend is unavailable.
4. Database is unavailable.
5. Camera is unavailable.
6. LPR service times out.
7. Unknown plate is detected.
8. Sensor reports invalid distance.
9. Battery reading is impossible.
10. Frontend cannot reach API.
11. Two nodes claim the same parking-space identifier.
12. Old cached data arrives after newer data.

---

# Security and Privacy Review

This system processes license plates and possibly vehicle images. Treat them as sensitive operational data.

Check:

- Secrets are not committed.
- `.env` files are excluded correctly.
- Default credentials are not used.
- Passwords are hashed using a suitable password-hashing method.
- Tokens are validated and expire.
- Role checks happen server-side.
- Administrator endpoints are protected.
- SQL/NoSQL queries are safe.
- Uploaded images are validated.
- Logs do not expose tokens, passwords, or unnecessary personal data.
- Plate/image retention is limited or documented.
- Transport security expectations are documented.
- ESP32 communication is authenticated when feasible.
- Devices cannot easily impersonate other node IDs.
- Debug endpoints are disabled or protected.
- CORS is not unrestricted without reason.
- Error messages do not expose stack traces in production.
- Dependency versions do not obviously introduce known critical risk.
- Privacy documentation explains what is collected and why.

Do not perform intrusive exploitation. Use safe static review and local testing only.

---

# Testing Quality Review

Evaluate whether tests cover real behavior rather than only trivial functions.

Report coverage for:

- Sensor threshold/calibration logic
- Occupancy state transitions
- Battery conversion
- Role/zone authorization
- Plate normalization
- LPR failure handling
- Violation generation
- Node offline detection
- Historical logging
- Statistics
- Recommendations
- Incentive points
- API authentication and authorization
- Frontend states
- End-to-end flow

Identify:

- Missing tests
- Flaky tests
- Tests that always pass
- Excessive mocking
- Tests requiring undocumented manual setup
- Test data containing real personal information

---

# Documentation Review

Check whether the repository explains:

- Project goal
- Architecture
- Hardware wiring
- Required parts
- Environment variables
- Local development
- Database setup
- Firmware setup and flashing
- ESP32-CAM setup
- Calibration
- Running the LPR service
- Running frontend/backend
- Tests
- Deployment
- Default users or seed data
- Security limitations
- Known limitations
- Demo procedure

Every required command should be copyable and consistent with the actual repository.

---

# Scoring

Score each category from 0 to 5:

| Score | Meaning |
|---:|---|
| 0 | Not implemented |
| 1 | Placeholder or minimal prototype |
| 2 | Significant partial implementation |
| 3 | Main flow works, but important gaps remain |
| 4 | Strong implementation with minor gaps |
| 5 | Complete, integrated, tested, and documented |

Score these categories:

1. Real-time availability
2. LPR and access control
3. Violation alerts
4. Accessible parking
5. Battery and maintenance
6. Device access display
7. Logs and statistics
8. Node configuration
9. Offline handling
10. Web GUI
11. Calibration
12. Recommendations
13. Incentive points
14. Security and privacy
15. Testing
16. Documentation and deployment

Calculate:

`Final percentage = (sum of category scores / maximum possible score) × 100`

Also provide:

- **Prototype readiness**
- **Demo readiness**
- **Pilot readiness**
- **Production readiness**

Use one of: Not Ready / Limited / Mostly Ready / Ready.

A high score is not allowed when critical security, authorization, stale-data, or safety failures remain.

---

# Prioritized Fix Plan

Organize fixes into:

## P0 – Must fix before any demo

Examples:

- Project does not build or start
- Main availability flow is broken
- Authorization grants access incorrectly
- Secrets are committed
- Standard users can access administrator functions
- Unknown/offline spaces are shown as definitely free

## P1 – Must fix before course submission or pilot

Examples:

- Major user story is incomplete
- No real database persistence
- No offline detection
- LPR is only mocked without clear disclosure
- Missing hardware calibration
- Missing meaningful tests

## P2 – Important improvement

Examples:

- Better retry behavior
- Better dashboard states
- More integration tests
- Improved documentation
- Better statistics

## P3 – Optional enhancement

Examples:

- UI polish
- Additional charts
- Performance optimizations not required for the expected scale

For every fix include:

- Affected requirement
- Exact files likely to change
- Technical approach
- Tests to add
- Estimated complexity: Small / Medium / Large
- Dependencies or blockers

Do not give time estimates.

---

# Final Report Template

Use this exact major structure in `PROJECT_AUDIT_REPORT.md`:

```markdown
# ParkMe Project Audit Report

## 1. Executive Summary

## 2. Repository and Architecture Overview

## 3. Commands Executed and Results

## 4. Requirement Traceability Matrix

## 5. Detailed User-Story Review
### Story 1 – Availability
### Story 2 – LPR Access
### Story 3 – Violation Alert
### Story 4 – Accessible Parking
### Story 5 – Maintenance
### Story 6 – Device Access Display
### Story 7 – Logs and Statistics
### Story 8 – Configuration
### Story 9 – Offline Handling
### Story 10 – Web GUI
### Story 11 – Calibration

## 6. Additional Requirements
### Spot Recommendations
### Incentive Points

## 7. Role and Authorization Review

## 8. Data Model and Database Review

## 9. API Review

## 10. LPR Review

## 11. Firmware and Hardware Review

## 12. Reliability and Failure Scenarios

## 13. Security and Privacy Review

## 14. Test Quality and Coverage

## 15. Documentation and Deployment Review

## 16. Missing, Partial, and Broken Features

## 17. Prioritized Fix Plan

## 18. Scores and Readiness Assessment

## 19. Final Verdict
```

---

# Final Verdict Rules

End with direct answers to all of these:

1. Does the repository implement the ParkMe project definition?
2. Which user stories are complete?
3. Which user stories are partial?
4. Which user stories are missing or broken?
5. Does the main end-to-end flow work?
6. Is LPR real or mocked?
7. Is authorization enforced securely?
8. Does offline handling prevent incorrect availability?
9. Can the project be demonstrated now?
10. What are the five most important next actions?

Be strict, evidence-based, and transparent. Do not describe an intended design as an implemented feature.
