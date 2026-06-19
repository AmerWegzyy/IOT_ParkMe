# Why We Migrated to Google Cloud and Firebase

This note explains why the repository moved away from the older Render + SQL stack and what the change means for the team.

## Why the Migration Happened

The migration was driven by three practical reasons:

1. Course and infrastructure requirements
   - The project needed to use Google Cloud and Firebase.
2. Budget and operations
   - The team can use Google Cloud credits on the shared Google account.
   - Cloud Run scales down when the system is idle.
3. Better fit for the current product
   - Firestore fits the event-driven parking model well.
   - Firebase Authentication is a cleaner web-login path than a custom backend login endpoint.
   - Google Cloud Vision replaces the heavier local OCR toolchain.

## What Changed

### Backend hosting

- Before: Render
- Now: Google Cloud Run

Impact:

- `Backend/render.yaml` was removed.
- `Backend/cloudbuild.yaml` was added.
- `Backend/Dockerfile` now matches Cloud Run deployment expectations.

### Database layer

- Before: SQL-based storage with schema and seed SQL files
- Now: Firebase Firestore

Impact:

- SQL queries in `Backend/main.py` were replaced with Firestore SDK calls.
- `Backend/schema.sql` and `Backend/seed.sql` were removed.
- `Backend/seed_firestore.py` was added.

### OCR pipeline

- Before: OpenCV + Tesseract inside the backend container
- Now: Google Cloud Vision API

Impact:

- `Backend/main.py` now calls Cloud Vision for text detection.
- `Backend/requirements.txt` now depends on `google-cloud-vision`.
- The Docker image no longer needs the old Tesseract stack.

### Web authentication

- Before: custom FastAPI login endpoint
- Now: Firebase Authentication

Impact:

- The frontend signs in directly with Firebase.
- The backend verifies Firebase ID tokens.
- The Firestore `users` collection remains the source of roles and display names.

### Frontend hosting

- Before: only served by the backend
- Now: still serveable by the backend, with Firebase Hosting added as the recommended static-hosting option

Impact:

- `firebase.json` and `.firebaserc` were added.
- `Frontend/index.html` loads Firebase SDKs.
- `Frontend/app.js` now uses Firebase Auth and a Cloud Run production URL.

## What Stayed Similar

These areas stayed mostly familiar:

- The FastAPI project structure is still the backend core.
- Most business endpoints remain under `/api/v1`.
- The frontend UI is still plain HTML/CSS/JS.
- The ESP32 firmware flow is still heartbeat plus image upload.

## What Changed for Daily Development

### Backend work

- New database reads and writes must use Firestore SDK calls instead of SQL.
- Local backend runs need Google credentials and a Firebase project.
- Some queries require Firestore composite indexes.

### Frontend work

- Local login now depends on Firebase web config.
- Production API calls should target the Cloud Run URL.

### Hardware work

- Firmware still needs a backend host and spot identifiers configured locally.
- The final deployed backend host must be copied into `ESP32/SECRETS.h`.
- Signed hardware traffic should use the same `ESP32_HMAC_SECRET` in firmware and backend.

## Read Next

- `Documentation/setup_guide.md`
- `Documentation/google_cloud_firebase_team_checklist.md`
- `Documentation/how_to_run_locally.md`
- `Documentation/migration_to_google_cloud_and_firebase.md`
- `Documentation/firestore_database_structure.md`
