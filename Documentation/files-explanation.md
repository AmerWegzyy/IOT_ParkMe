# ParkMe Documentation Index

Welcome to the newly compacted ParkMe documentation. To reduce clutter, duplicate historical logs and architectural development chats have been safely archived to `docs/archive/`.

The active, authoritative documentation for the current state of the ParkMe system is stored here in the `Documentation/` folder.

## Active Manuals

1. **`setup_guide.md`**
   * Read this first. It covers Firebase configuration, Python `.env` requirements, service accounts, database seeding, and the critical step for generating Firestore Composite Indexes so the server doesn't crash on boot.

2. **`system_architecture.md`**
   * The big picture. Explains the Edge-Push architecture, how the ultrasonic and camera nodes interact with the FastAPI backend, and how Server-Sent Events (SSE) provide real-time DOM updates to the frontend.

3. **`api_and_database.md`**
   * The data layer. Details the exact schema of the 4 Firestore collections (`users`, `vehicles`, `parking_spots`, `parking_logs`), how hardware nodes map via `sensor_mac` and `camera_mac`, and the REST API endpoints.

4. **`hardware_and_edge_cases.md`**
   * The chaos handling. Explains how the ESP32 C++ code handles network disconnections (NVS caching), adaptive calibration, and debouncing. Details how the Python backend mathematically deduces hardware failures (Ghost Logs) and prevents issuing tickets for drivers aborting a parking attempt.

---

## The Archive

If you are looking for the original AI/development chat logs, bug reports, or deprecated phase checkpoints, they have been moved to:
`../docs/archive/`
