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

- `Backend/` — FastAPI backend, Firestore seeding script, Dockerfile, and Cloud Build deployment config
- `Frontend/` — HTML/CSS/JS dashboard
- `ESP32/` — sensor firmware, camera firmware, and shared Arduino libraries
- `Documentation/` — the project overview doc (`PROJECT_OVERVIEW.md`)
- `Unit Tests/` — hardware validation sketches (ultrasonic, camera, OLED)
- `tests/` — Python unit tests for the backend logic

## Start Here

- `Documentation/PROJECT_OVERVIEW.md` — the complete, code-verified guide: architecture, backend logic, database schema, firmware, frontend, timings, edge cases, local run/seed/deploy instructions, and testing assets
- `Documentation/LOCAL_TESTING_GUIDE.md` — flash the boards, run the backend locally, verify end-to-end, then the exact steps to move to the cloud
- `Documentation/CLOUD_DEPLOYMENT_GUIDE.md` — deploying the backend to Google Cloud Run: prerequisites, required code fixes, deploy commands, troubleshooting, and the full `SECRETS.h` checklist
- `ESP32/hardware-upload-guide.md` — how to configure `SECRETS.h` and flash both microcontrollers
- `Unit Tests/README.md` — hardware validation sketches and expected results

## Important Security Notes

- Never commit `serviceAccountKey.json`.
- Never commit `.env` files with local values.
- Never commit `ESP32/SECRETS.h`; keep only `ESP32/SECRETS.example.h` in Git.
- Complete Google Cloud, Firebase, and account provisioning manually through the team-owned Google account.

This project is part of ICST, The Interdisciplinary Center for Smart Technologies, Taub Faculty of Computer Science, Technion.
