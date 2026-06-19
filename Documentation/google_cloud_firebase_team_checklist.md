# Google Cloud and Firebase Team Checklist

Use the shared project Google account for these steps:

- `iot670619@gmail.com`

All passwords, 2FA codes, API secrets, and private keys must stay out of Git and out of team chat logs.

## Team Setup Checklist

- [ ] Redeem the Google Cloud coupon on the shared project account
- [ ] Create the Google Cloud Project
- [ ] Record the final Google Cloud / Firebase project ID
- [ ] Enable Firebase for that project
- [ ] Enable Firestore
- [ ] Enable Firebase Authentication
- [ ] Enable Cloud Run
- [ ] Enable Cloud Build
- [ ] Enable Cloud Vision API
- [ ] Create the Firebase Web App
- [ ] Create a service account for local backend development
- [ ] Download `serviceAccountKey.json` locally
- [ ] Confirm `serviceAccountKey.json` is not committed to GitHub
- [ ] Confirm local `.env` files are not committed to GitHub
- [ ] Update `.firebaserc` to the real project ID
- [ ] Update `Frontend/app.js` Firebase web config placeholders
- [ ] Update `Frontend/app.js` with the real Cloud Run URL after deployment
- [ ] Copy `Backend/.env.example` to `Backend/.env` locally
- [ ] Set `GOOGLE_APPLICATION_CREDENTIALS`
- [ ] Set `FIREBASE_PROJECT_ID`
- [ ] Set `ESP32_HMAC_SECRET` if signed hardware traffic will be enabled
- [ ] Seed Firestore with `python seed_firestore.py`
- [ ] Create Firebase Auth users whose emails match Firestore `users` documents
- [ ] Run the backend locally and test `http://localhost:8000/docs`
- [ ] Deploy the backend to Cloud Run
- [ ] Deploy the frontend to Firebase Hosting
- [ ] Create Firestore indexes when prompted by first-use queries
- [ ] Copy `ESP32/SECRETS.example.h` to local `ESP32/SECRETS.h`
- [ ] Set the final backend host in `ESP32/SECRETS.h`
- [ ] Align firmware spot identifiers with the Firestore spot records

## Manual Configuration Outputs the Team Should Save

Record these values somewhere safe for the team:

- Google Cloud Project ID
- Firebase project ID
- Cloud Run backend URL
- Firebase web config values
- Firestore region
- whether HMAC signing is enabled for ESP32 requests

## Quick Security Review

Before anyone pushes:

- [ ] `serviceAccountKey.json` is local only
- [ ] `Backend/.env` is local only
- [ ] `ESP32/SECRETS.h` is local only
- [ ] no private keys or passwords were pasted into tracked files
