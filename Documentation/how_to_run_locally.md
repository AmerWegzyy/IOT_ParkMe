# How to Run ParkMe Locally

This guide is for local development after the migration to Google Cloud and Firebase.

## What You Need First

Before local development works end-to-end, the team must already have:

- a Google Cloud Project
- Firebase enabled
- Firestore enabled
- Firebase Authentication enabled
- Cloud Vision API enabled
- a service-account JSON key downloaded locally

If that setup is not done yet, complete `Documentation/setup_guide.md` first.

## 1. Backend Setup

From `Backend/`:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Copy the example env file:

```powershell
Copy-Item .env.example .env
```

Fill the local values in `.env`:

```env
GOOGLE_APPLICATION_CREDENTIALS=./serviceAccountKey.json
FIREBASE_PROJECT_ID=your-gcp-project-id
ESP32_HMAC_SECRET=change-me-before-production
ENVIRONMENT=development
PORT=8000
```

Place the downloaded Firebase Admin key at:

- `Backend/serviceAccountKey.json`

## 2. Seed Firestore

From `Backend/`:

```powershell
.\.venv\Scripts\Activate.ps1
python seed_firestore.py
```

This seeds Firestore collections, but it does not create Firebase Auth users.

## 3. Create Matching Firebase Auth Users

The frontend can only log in through Firebase Auth.

For each Firestore user you want to test with:

1. Open Firebase Authentication.
2. Create an Email/Password user.
3. Use the same email as the Firestore user document.

Without this step:

- `signInWithEmailAndPassword` will fail in the frontend
- backend token verification may succeed only for users that also exist in Firestore

## 4. Start the Backend

From `Backend/`:

```powershell
.\.venv\Scripts\Activate.ps1
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Open:

- `http://localhost:8000/`
- `http://localhost:8000/docs`

## 5. Configure the Frontend for Local Login

The local frontend uses the fallback Firebase config in `Frontend/app.js`.

Update these values with the Firebase Web App config from Firebase Console:

- `apiKey`
- `authDomain`
- `projectId`
- `storageBucket`
- `messagingSenderId`
- `appId`

Notes:

- These values identify the Firebase web app.
- They are not the same as the Admin service-account JSON.
- When the frontend is served from Firebase Hosting, `/__/firebase/init.js` can provide this config automatically.

## 6. What Works Locally

With real Firebase and Google Cloud services configured, you can test:

- backend API routes
- Firebase-authenticated dashboard login
- Firestore reads and writes
- OCR through Google Cloud Vision
- SSE dashboard updates

## 7. What Does Not Work Without Cloud Setup

Without Firebase and Google Cloud configured, you cannot fully test:

- web login
- Firestore-backed backend behavior
- Cloud Vision OCR
- full end-to-end dashboard and hardware flows

You can still test some pieces in isolation:

- ESP32 firmware boot and sensors
- camera boot and LCD behavior
- frontend layout and non-auth UI
- backend imports and static-file serving

## 8. ESP32 Local Testing Notes

Before firmware tests:

1. Copy `ESP32/SECRETS.example.h` to `ESP32/SECRETS.h`.
2. Fill in Wi-Fi values locally.
3. Point the backend host to your current backend target.
4. Align the configured spot identifiers with the Firestore records you are testing against.

## 9. Common Pitfalls

- `serviceAccountKey.json` missing locally
- Firebase Auth user exists, but matching Firestore `users` document does not
- Firestore user exists, but Firebase Auth user does not
- `YOUR_CLOUD_RUN_URL` still left in `Frontend/app.js`
- firmware host still points at an old Render or placeholder URL
- Firestore indexes not created yet
