# ParkMe

ParkMe is a smart parking system built around ESP32 hardware, a FastAPI backend, and a web dashboard.

The current production architecture is:

- ESP32 sensor and camera nodes at the edge
- FastAPI backend deployed to Google Cloud Run
- Firebase Firestore for application data
- Firebase Authentication for web login
- Google Cloud Vision API for license-plate OCR
- Optional Firebase Hosting for the static frontend

## Repository Layout

- `Backend/` — FastAPI backend, Firestore seeding script, multi-spot simulator (`simulate_spots.py`), Dockerfile, and Cloud Build deployment config
- `Frontend/` — HTML/CSS/JS dashboard
- `ESP32/` — sensor firmware, camera firmware, and shared Arduino libraries
- `Documentation/` — all project docs; start at `Documentation/README.md`
- `Unit Tests/` — hardware validation sketches (ultrasonic, camera, OLED)
- `tests/` — Python unit tests + the 31-image LPR pipeline suite

## Start Here

- `Documentation/README.md` — **the documentation index**: which doc to read for what, in order
- `Documentation/SYSTEM_EXPLAINED.md` — the full technical deep dive: ESP-NOW design rationale, dual-core firmware, calibration, WiFi-loss handling, memory/buffers, and how every component talks to the others
- `Documentation/PROJECT_OVERVIEW.md` — the complete reference: architecture, backend logic, database schema, firmware, frontend, timings, edge cases
- `Documentation/TESTING_GUIDE.md` — how to test everything, including simulating a full parking lot with `Backend/simulate_spots.py`
- `ESP32/hardware-upload-guide.md` — how to configure `SECRETS.h` and flash both microcontrollers

## Important Security Notes

- Never commit `serviceAccountKey.json`.
- Never commit `.env` files with local values.
- Never commit `ESP32/SECRETS.h`; keep only `ESP32/SECRETS.example.h` in Git.
- Complete Google Cloud, Firebase, and account provisioning manually through the team-owned Google account.

This project is part of ICST, The Interdisciplinary Center for Smart Technologies, Taub Faculty of Computer Science, Technion.
