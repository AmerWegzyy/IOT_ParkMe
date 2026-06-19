# ParkMe Setup Guide

This guide describes the current Google Cloud + Firebase setup for ParkMe.

Use the shared project Google account for the cloud-side setup:

- `iot670619@gmail.com`

Do not store or commit passwords, 2FA codes, service-account keys, or local `.env` files.

## 1. Create the Cloud Project

1. Sign in to Google with the shared project account.
2. Redeem the GCP coupon on that account.
3. Create a new Google Cloud Project for ParkMe.
4. Record the final project ID. You will use it in:
   - `Backend/.env`
   - `.firebaserc`
   - the Firebase web config in `Frontend/app.js`

## 2. Enable the Required Services

Enable these products and APIs for the same project:

- Firebase
- Firestore Database
- Firebase Authentication
- Cloud Run
- Cloud Build
- Cloud Vision API

Recommended:

- Firebase Hosting for the static web UI

If you deploy with the current `Backend/cloudbuild.yaml`, make sure the project can build and push `gcr.io/$PROJECT_ID/parkme-backend`.

## 3. Configure Firebase

### Firestore

1. Open Firebase Console.
2. Link it to the Google Cloud Project.
3. Create a Firestore database.
4. Choose the region your team wants to keep using consistently.

### Authentication

1. Open Firebase Authentication.
2. Enable the `Email/Password` sign-in provider.
3. Create the test users the team needs.

Important:

- Firebase Auth stores the login credentials.
- Firestore stores the user profile and role.
- The email in Firebase Auth must match the email in the Firestore `users` collection.

### Web App

1. Register a Firebase Web App.
2. Copy the Firebase web config values.
3. Update the fallback config in `Frontend/app.js` for local development.
4. If you use Firebase Hosting, `/__/firebase/init.js` will inject the hosted config automatically.

## 4. Create a Service Account for Local Backend Development

1. Open Firebase Console or Google Cloud Console.
2. Create or select a service account with Firestore and Vision access.
3. Download the JSON key file.
4. Save it locally as `Backend/serviceAccountKey.json`.

Security rules:

- `serviceAccountKey.json` must stay local.
- It is ignored by Git.
- Do not upload it to GitHub or paste it into docs.

## 5. Configure Local Environment Variables

Copy `Backend/.env.example` to `Backend/.env` and fill in the real values locally.

Expected variables:

```env
GOOGLE_APPLICATION_CREDENTIALS=./serviceAccountKey.json
FIREBASE_PROJECT_ID=your-gcp-project-id
ESP32_HMAC_SECRET=change-me-before-production
ENVIRONMENT=development
PORT=8000
```

Notes:

- `GOOGLE_APPLICATION_CREDENTIALS` is needed locally.
- `FIREBASE_PROJECT_ID` should match the Google Cloud / Firebase project ID.
- `ESP32_HMAC_SECRET` should match the firmware only when you enable signed ESP32 requests.
- On Cloud Run, Application Default Credentials come from the runtime service account instead of the local JSON file.

## 6. Install the Backend Locally

From `Backend/`:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 7. Seed Firestore

Run:

```powershell
cd Backend
.\.venv\Scripts\Activate.ps1
python seed_firestore.py
```

The seeding script creates sample documents in:

- `parking_spots`
- `users`
- `vehicles`
- `parking_logs`

Important:

- The seeder only writes Firestore data.
- It does not create Firebase Auth users automatically.
- Create matching Firebase Auth users manually for any emails you want to log in with.

## 8. Run the Backend Locally

From `Backend/`:

```powershell
.\.venv\Scripts\Activate.ps1
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Useful URLs:

- Backend API: `http://localhost:8000`
- Swagger UI: `http://localhost:8000/docs`
- Frontend served by FastAPI: `http://localhost:8000/`

## 9. Deploy the Backend to Cloud Run

From `Backend/`:

```powershell
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
gcloud services enable run.googleapis.com cloudbuild.googleapis.com vision.googleapis.com
gcloud builds submit --config cloudbuild.yaml
```

After deployment:

1. Copy the Cloud Run URL.
2. Replace `YOUR_CLOUD_RUN_URL` in `Frontend/app.js`.
3. Update the ESP32 backend host in `ESP32/SECRETS.h`.

## 10. Deploy the Frontend

Recommended option:

- Deploy `Frontend/` using Firebase Hosting with the existing `firebase.json`.

Remember to update `.firebaserc` to the real Firebase project ID before running `firebase deploy`.

## 11. Firestore Indexes

Some queries require Firestore composite indexes.

When an endpoint returns an index error:

1. Open the link provided in the error.
2. Create the suggested index.
3. Wait for the index to finish building.

The main query patterns are documented in `Documentation/firestore_database_structure.md`.

## 12. Firmware Integration

Before live ESP32 tests:

1. Copy `ESP32/SECRETS.example.h` to `ESP32/SECRETS.h`.
2. Set Wi-Fi credentials locally.
3. Set the Cloud Run host.
4. Align the firmware spot identifiers with the Firestore spot records you created.
5. Set the same HMAC secret in firmware and backend if you want signed device traffic.

## Quick Checklist

- [ ] GCP coupon redeemed on `iot670619@gmail.com`
- [ ] Google Cloud Project created
- [ ] Firebase enabled
- [ ] Firestore enabled
- [ ] Firebase Authentication enabled
- [ ] Cloud Run enabled
- [ ] Cloud Build enabled
- [ ] Cloud Vision API enabled
- [ ] Service account created and JSON key downloaded locally
- [ ] Local `.env` configured
- [ ] Firestore seeded
- [ ] Firebase Auth users created
- [ ] Backend tested locally
- [ ] Backend deployed to Cloud Run
- [ ] Frontend deployed or configured for Firebase Hosting
- [ ] ESP32 firmware updated with the deployed backend host
