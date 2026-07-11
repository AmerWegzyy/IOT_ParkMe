# Claude Code Prompt — Audit ParkMe Against All User Stories

You are working inside the ParkMe repository.

Your task is to perform a fresh, code-first audit of the complete project against `USER_STORIES.md`.

## Important current context

- The project has already been deployed to Google Cloud Run.
- The main system architecture is ESP32/ESP32-CAM → FastAPI → Google Cloud Vision → Firestore → web dashboard/OLED.
- Calibration has recently been fixed and is reported working.
- OCR/LPR has recently been fixed and tested.
- Do not assume those features are perfect; verify the current implementation and current test evidence.
- Old audit documents may be stale. In particular, do not copy statuses or conclusions from an older `PROJECT_AUDIT_REPORT.md`.
- Treat current source code, current tests, current configuration templates, and reproducible runtime evidence as the source of truth.
- Never print or commit secrets from `.env`, `env`, `serviceAccountKey.json`, or `ESP32/SECRETS.h`.

## Scope

Read the entire relevant repository, including:

- `Backend/**/*.py`
- `Frontend/**/*`
- `ESP32/**/*.ino`
- `ESP32/**/*.h`
- `tests/**/*`
- `Unit Tests/**/*`
- deployment files such as Dockerfile, Cloud Build, Firebase config, requirements, `.dockerignore`, and environment templates
- current documentation that describes architecture or operation

Ignore generated binaries, caches, virtual environments, Git internals, and image contents unless they are specifically part of an OCR test.

Record the current branch and commit SHA at the beginning of the report.

## Rules for judging a user story

Use exactly one of these statuses:

- `DONE`
- `PARTIAL`
- `MISSING`
- `BROKEN`
- `NOT TESTABLE`

A story is `DONE` only when:

1. The complete user flow exists across all required layers.
2. The implementation is connected to the real runtime path.
3. Important failures and edge cases are handled.
4. There is convincing automated test evidence, hardware evidence, cloud evidence, or a clearly reproducible manual verification.

Do not mark a story DONE merely because:

- a function or endpoint exists;
- documentation claims it works;
- a Firestore field exists;
- frontend code displays a value that the backend does not guarantee;
- a test file exists but was not run or is stale;
- code is unreachable or configured only in a seed script.

## Required work

### 1. Build a repository inventory

List the major components, responsibilities, important entry points, and data flows:

- sensor firmware;
- camera firmware;
- shared firmware helpers;
- FastAPI backend;
- Firestore collections;
- Firebase authentication;
- Google Vision OCR;
- frontend;
- OLED/display communication;
- tests;
- deployment.

Identify dead code, duplicate implementations, stale tests, and documentation/code contradictions.

### 2. Trace every requirement

Audit every item in `USER_STORIES.md`:

- `US-01` through `US-11`;
- `R-01` spot recommendations;
- `R-02` incentive points;
- all cross-cutting quality requirements.

For each requirement:

1. Restate the requirement briefly.
2. Assign a status.
3. Provide exact evidence using file paths, function/class names, and line numbers.
4. Describe the complete implemented flow.
5. List every acceptance criterion that is not satisfied.
6. List relevant tests and whether they actually ran.
7. State user impact and technical risk.
8. Give a specific recommended change.
9. Estimate effort as `S`, `M`, or `L`.
10. Assign priority:
   - `P0` — blocks the core demo or can produce dangerous/incorrect authorization;
   - `P1` — required story gap or major reliability problem;
   - `P2` — quality, maintainability, UX, or production-hardening improvement.

### 3. Verify calibration carefully

Do not rely on the old audit.

Trace the exact path:

- calibration button;
- sample collection;
- invalid measurement handling;
- stored baseline;
- NVS/Preferences persistence;
- threshold calculation;
- threshold loading after reboot;
- the exact occupancy classification call site.

Confirm whether a changed calibration value truly changes detection behavior.

Report whether calibration metadata exists only on the device or is also visible to the backend/admin. Treat backend visibility as an improvement unless the original story explicitly requires it.

### 4. Verify OCR/LPR carefully

Trace:

- fresh frame capture;
- FIFO flush behavior;
- upload retries;
- `/api/v1/sensors/park`;
- Google Vision calls;
- plate extraction and 7/8-digit validation;
- Firestore vehicle/user lookup;
- role/category authorization;
- duplicate/session handling;
- unreadable-image manual review;
- evidence storage.

Run or inspect:

- plate-extraction unit tests;
- the image-based LPR pipeline test;
- the latest stored LPR results.

Do not describe OCR as 100% reliable unless the current image test set passes 100%. Report exact pass/fail counts and investigate every failure.

### 5. Check likely remaining gaps without assuming they exist

Investigate these as hypotheses:

- incentive points may be missing;
- admin node configuration may exist only through Firestore/seed scripts;
- low-battery alerts may be missing even if battery display exists;
- violation/offline alerts may work only while the dashboard is open;
- offline telemetry may preserve only the latest state rather than full event history;
- stale/offline status may be frontend-only;
- logs/statistics may lack date filters, pagination, retention, or bounded Firestore queries;
- frontend mobile/error states may be incomplete;
- integration coverage for the large backend state machine may be weak;
- an old SQLite test may still be stale;
- hardware endpoints may rely only on MAC addresses;
- CORS or TLS verification may be too permissive;
- in-memory SSE/display queues may conflict with Cloud Run scaling.

For each hypothesis, prove or disprove it from current code.

### 6. Run safe checks

Run all safe tests and static checks available in the repository. At minimum, try:

```bash
python -m unittest discover -s tests -v
python -m py_compile Backend/main.py Backend/parking_logic.py
```

Also run any documented LPR test that can execute with the available server and credentials.

For firmware:

- inspect compile-time tests;
- compile only if the Arduino toolchain and required libraries are available;
- otherwise mark compilation as NOT TESTABLE and give the exact command or IDE steps required.

Do not modify production data. Do not run destructive seed scripts against the live Firestore project.

### 7. Review deployment readiness

Check:

- Cloud Run container and `$PORT`;
- production credentials through ADC;
- excluded secrets;
- CORS;
- Firebase Hosting API URL;
- Firestore and Vision service configuration;
- instance scaling and in-memory state;
- timeouts;
- health/readiness behavior;
- logging;
- rollback and repeatable deployment.

Separate:
- course-prototype acceptable risks;
- demo blockers;
- pilot blockers;
- production blockers.

## Required output

Create:

`Documentation/USER_STORY_IMPLEMENTATION_AUDIT.md`

Use this structure:

1. Executive summary.
2. Branch, commit, audit date, and commands run.
3. Architecture and repository inventory.
4. Requirement traceability matrix.
5. Detailed review of every user story.
6. Cross-cutting findings.
7. Test results.
8. Deployment findings.
9. Prioritized improvement backlog.
10. Suggested implementation order.
11. Documentation/code contradictions.
12. Final readiness:
    - Prototype;
    - Demo;
    - Pilot;
    - Production.

The traceability matrix must contain:

| ID | Requirement | Status | Code evidence | Test/runtime evidence | Main gap | Risk | Priority | Effort |
|---|---|---|---|---|---|---|---|---|

## Improvement backlog format

For every recommended task, include:

- task title;
- affected story IDs;
- problem;
- user impact;
- files likely to change;
- implementation approach;
- acceptance test;
- priority;
- effort;
- dependencies.

Group tasks into:

1. Core correctness.
2. Required missing stories.
3. Reliability and offline behavior.
4. Testing.
5. Security.
6. UX.
7. Maintainability and documentation.

## Final behavior

- Do not change code during this audit.
- Do not hide failing tests.
- Do not use old audit scores as evidence.
- Be explicit when hardware or cloud credentials prevent verification.
- Prefer exact file/line evidence over general statements.
- Finish by listing the five highest-value improvements in the order they should be implemented.
