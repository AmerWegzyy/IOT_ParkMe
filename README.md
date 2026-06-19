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
- `Documentation/` — current setup, migration, and architecture docs
- `docs/` — older design notes and historical writeups

## Start Here

Use the current docs in `Documentation/`:

- `Documentation/setup_guide.md` — first-time Google Cloud + Firebase setup
- `Documentation/google_cloud_firebase_team_checklist.md` — shared team checklist
- `Documentation/how_to_run_locally.md` — local backend/frontend workflow
- `Documentation/migration_to_google_cloud_and_firebase.md` — migration summary and file-level diff
- `Documentation/firestore_database_structure.md` — Firestore collections and indexes
- `Documentation/system_architecture_and_workflow.md` — current end-to-end architecture
- `Documentation/why_we_migrated.md` — short explanation of the migration and its impact

## Important Security Notes

- Never commit `serviceAccountKey.json`.
- Never commit `.env` files with local values.
- Never commit `ESP32/SECRETS.h`; keep only `ESP32/SECRETS.example.h` in Git.
- Complete Google Cloud, Firebase, and account provisioning manually through the team-owned Google account.

This project is part of ICST, The Interdisciplinary Center for Smart Technologies, Taub Faculty of Computer Science, Technion.
