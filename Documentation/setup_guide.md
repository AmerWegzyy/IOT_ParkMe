# ParkMe — Local Setup & Deployment Guide

This guide covers setting up the ParkMe backend with Google Cloud and Firebase.

---

## Prerequisites
- Python 3.11+
- Google Cloud SDK (`gcloud`)
- A Google account with Firebase access

---

## 1. Firebase & Firestore Setup
1. Go to the Firebase Console and create a project (e.g., `parkme-technion`).
2. Click **Build → Firestore Database** and create a database in `europe-west1` or `me-west1` in Test Mode.
3. Go to **Project Settings → Service accounts**, generate a new private key for the Firebase Admin SDK.
4. Rename the downloaded file to `serviceAccountKey.json` and place it in the `Backend/` directory. **(DO NOT COMMIT THIS FILE)**.

---

## 2. Local Backend Setup
```bash
cd Backend/
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit your `.env` file:
```ini
GOOGLE_APPLICATION_CREDENTIALS=./serviceAccountKey.json
JWT_SECRET=your_jwt_secret_here
ENVIRONMENT=development
PORT=8000
FIREBASE_PROJECT_ID=parkme-technion
```

---

## 3. Database Seeding
Populate your empty database with the current MAC schema (`sensor_mac` & `camera_mac`):
```bash
python seed_firestore.py
```
*(Note: `.set()` operations are idempotent. It wipes the spots and logs, but safely updates users/vehicles without creating duplicates).*

---

## 4. Run the Server
```bash
uvicorn main:app --reload
```
- API & Swagger: `http://localhost:8000/docs`
- Web Frontend: `http://localhost:8000/`

---

## 5. Composite Index Requirements (IMPORTANT)
The first time you run a heartbeat request or trigger an API call that queries `parking_logs` for `exit_time == None` ordered by `entry_time DESC`, your server will crash with a **500 FailedPrecondition** error.
1. Look at your `uvicorn` terminal output.
2. CTRL+Click the URL generated in the error message.
3. The Firebase Console will open and automatically build the required Composite Index.
4. Wait 1-2 minutes for it to say "Enabled", then try your request again.
