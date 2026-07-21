# ParkMe Documentation — Start Here

One page telling you which document to open for what, in a sensible reading order.

## Understand the project

| # | Document | What it gives you |
|---|---|---|
| 1 | [SYSTEM_EXPLAINED.md](SYSTEM_EXPLAINED.md) | **The deep dive** — how everything works and *why* it was built this way: ESP-NOW vs cables, dual-core design, calibration, WiFi-loss handling, buffers/PSRAM/NVS, how the boards talk to each other and to the cloud. Read this to present or defend the project. |
| 2 | [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md) | **The reference** — every API endpoint, Firestore collection, timing constant, sentinel state, and component, with file paths. Look things up here. |
| ★ | [HARDWARE_WIRING.md](HARDWARE_WIRING.md) | Wiring/connection diagram for both boards — pin tables, power notes, ESP-NOW + cloud links. |
| ★ | [VERSIONS.md](VERSIONS.md) | Exact software stack versions — ESP32 core/SDK, all Python packages, Firebase JS SDK, cloud services. |

## Run and test it

| # | Document | What it gives you |
|---|---|---|
| 7 | `Backend/simulate_spots.py` | Simulate the whole parking lot (spots A1–C2) with one command — real heartbeats and real photos through the real OCR pipeline, so the dashboard looks alive with only one physical device. `python Backend/simulate_spots.py --help` |
| 8 | [../ESP32/hardware-upload-guide.md](../ESP32/hardware-upload-guide.md) + [../ESP32/README.md](../ESP32/README.md) | Flashing the boards, calibration procedure, pins. |
| 9 | [../Unit Tests/README.md](../Unit%20Tests/README.md) | Hardware bring-up sketches (ultrasonic, OLED, camera) with PASS/FAIL serial output. |

## Live system

- Dashboard: <https://parkme-technion-f280b.web.app>
- Backend: `https://parkme-backend-31114651685.me-west1.run.app` (`/docs` for the API)

> ⚠️ Operational warning that outranks everything else: **do not run `Backend/seed_firestore.py` casually** — it wipes all parking spots including the real hardware MACs on C1.
