# Migration to Google Cloud and Firebase

This document summarizes the repository migration from the older Render + SQL stack to the current Google Cloud + Firebase architecture.

## Scope Reviewed

The migration spans the commits that moved the project from the pre-migration baseline to current `main`.

Key milestones:

- `2a1a2e5` — migrate backend to Google Cloud Run and Firebase Firestore
- `1053f73` — migrate OCR to Google Cloud Vision and prepare Firebase Hosting
- `069b442` — migrate authentication to Firebase Auth and remove legacy SQL auth pieces

Pre-migration baseline used for comparison:

- `75731c4`

## High-Level Architecture Change

Before:

- Render for backend hosting
- SQL database files and SQL query logic
- OpenCV/Tesseract OCR in the backend image
- custom backend login flow

After:

- Google Cloud Run for backend hosting
- Firebase Firestore for application data
- Google Cloud Vision API for OCR
- Firebase Authentication for dashboard login
- Firebase Hosting support for the static frontend

## Files Changed by Migration Area

### Google Cloud Run

- `Backend/render.yaml` — removed
- `Backend/cloudbuild.yaml` — added
- `Backend/Dockerfile` — updated for Cloud Run runtime expectations

What changed:

- deployment target moved away from Render
- backend container now expects Cloud Run to inject `PORT`
- Cloud Build pipeline now deploys `parkme-backend`

### Firebase Firestore

- `Backend/main.py` — SQL access replaced by Firestore SDK calls
- `Backend/schema.sql` — removed
- `Backend/seed.sql` — removed
- `Backend/seed_firestore.py` — added
- `Documentation/firestore_database_structure.md` — added

What changed:

- users, vehicles, parking spots, and parking logs now live in Firestore collections
- SQL joins were replaced by multi-step Firestore lookups in Python
- hardware heartbeats now resolve parking spots by `mac_address`

### Firebase Authentication

- `Frontend/index.html` — Firebase SDKs added
- `Frontend/app.js` — login flow moved to Firebase Auth
- `Backend/main.py` — protected endpoints now verify Firebase ID tokens

What changed:

- the old backend login endpoint was removed
- the browser signs in directly with Firebase Auth
- backend role lookup still comes from Firestore user documents

### Google Cloud Vision API

- `Backend/main.py` — OCR switched to `vision.ImageAnnotatorClient`
- `Backend/requirements.txt` — `google-cloud-vision` added
- `Backend/Dockerfile` — old OCR stack removed

What changed:

- image OCR no longer depends on local OpenCV/Tesseract processing
- backend needs Vision API access through Google credentials

### Firebase Hosting

- `firebase.json` — added
- `.firebaserc` — added
- `Frontend/app.js` — production API base now points to Cloud Run

What changed:

- the frontend can now be deployed separately as a static site
- production frontend config should target the deployed Cloud Run backend

## Repository-Level Diff from the Pre-Migration Baseline

Files added:

- `.firebaserc`
- `Backend/cloudbuild.yaml`
- `Backend/seed_firestore.py`
- `Documentation/firestore_database_structure.md`
- `Documentation/setup_guide.md`
- `Documentation/system_architecture_and_workflow.md`
- `Documentation/why_we_migrated.md`
- `firebase.json`

Files removed:

- `Backend/render.yaml`
- `Backend/schema.sql`
- `Backend/seed.sql`

Files updated:

- `.gitignore`
- `Backend/.env.example`
- `Backend/Dockerfile`
- `Backend/main.py`
- `Backend/requirements.txt`
- `Frontend/app.js`
- `Frontend/index.html`
- `docs/api_documentation.md`
- `docs/project_summary.md`

## Behavioral Changes

### Changed

- backend deployment path
- database access model
- OCR provider
- web authentication flow
- recommended static hosting path

### Mostly unchanged

- core business API routes under `/api/v1`
- frontend dashboard structure
- ESP32 heartbeat and image-upload concepts
- SSE-based live dashboard updates

## Important Follow-Up Items

The migration is structurally complete in the repo, but these manual or engineering tasks still matter:

1. Finish Google Cloud and Firebase project provisioning.
2. Create Firebase Auth users that match Firestore user emails.
3. Replace placeholder frontend Firebase config values.
4. Replace `YOUR_CLOUD_RUN_URL` with the real Cloud Run URL.
5. Update local `ESP32/SECRETS.h` with Wi-Fi, backend host, and the final HMAC secret if used.
6. Align firmware spot identifiers with Firestore spot IDs before full hardware integration testing.
