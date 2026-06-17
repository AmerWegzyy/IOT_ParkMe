# ParkMe — Setup Guide

Step-by-step instructions to set up the ParkMe backend from scratch with Google Cloud and Firebase.

---

## Prerequisites

Make sure you have the following installed on your machine:

- **Python 3.11+** — [Download](https://www.python.org/downloads/)
- **Google Cloud SDK (`gcloud`)** — [Install Guide](https://cloud.google.com/sdk/docs/install)
- **Git** — [Download](https://git-scm.com/)
- A Google account with Cloud/Firebase credits (Technion coupon)

---

## Step 1: Create a Firebase Project

1. Go to the [Firebase Console](https://console.firebase.google.com/)
2. Click **"Create a project"**
3. Enter a project name (e.g., `parkme-technion`)
4. Choose whether to enable Google Analytics (not required — you can skip)
5. Click **"Create project"**
6. Wait for it to finish, then click **"Continue"**

---

## Step 2: Enable Firestore Database

1. In the Firebase Console sidebar, click **"Build" → "Firestore Database"**
2. Click **"Create database"**
3. Choose a location — pick **`europe-west1` (Belgium)** or **`me-west1` (Tel Aviv)** if available
4. Start in **"Test mode"** (allows read/write without auth rules — fine for development)
5. Click **"Create"**

---

## Step 3: Download the Service Account Key

This JSON file lets your backend authenticate with Firebase.

1. In the Firebase Console, click the **⚙️ gear icon → "Project settings"**
2. Go to the **"Service accounts"** tab
3. Make sure **"Firebase Admin SDK"** is selected
4. Click **"Generate new private key"**
5. Click **"Generate key"** — a JSON file will download
6. **Rename** it to `serviceAccountKey.json`
7. **Move** it into the `Backend/` directory of the project

> ⚠️ **NEVER commit this file to Git.** It is already in `.gitignore`.

---

## Step 4: Set Up Google Cloud Project

Your Firebase project automatically creates a Google Cloud project with the same name.

```bash
# 1. Login to Google Cloud
gcloud auth login

# 2. Set your project (use the same project ID as Firebase)
gcloud config set project YOUR_PROJECT_ID

# 3. Enable required APIs
gcloud services enable run.googleapis.com
gcloud services enable cloudbuild.googleapis.com
gcloud services enable containerregistry.googleapis.com
gcloud services enable firestore.googleapis.com
```

> **How to find your project ID:** In Firebase Console → Project Settings → you'll see the "Project ID" field.

---

## Step 5: Set Up the Backend Locally

```bash
# 1. Navigate to the Backend directory
cd Backend/

# 2. Create a Python virtual environment
python3 -m venv venv

# 3. Activate it
source venv/bin/activate    # macOS/Linux
# venv\Scripts\activate     # Windows

# 4. Install dependencies
pip install -r requirements.txt

# 5. Copy the environment file and edit it
cp .env.example .env
```

Now edit the `.env` file:
```
GOOGLE_APPLICATION_CREDENTIALS=./serviceAccountKey.json
JWT_SECRET=your_jwt_secret_here
ENVIRONMENT=development
PORT=8000
```

---

## Step 6: Seed the Database with Test Data

This populates Firestore with sample users, vehicles, parking spots, and logs.

```bash
# Make sure you're in Backend/ with venv activated
export GOOGLE_APPLICATION_CREDENTIALS=./serviceAccountKey.json
python seed_firestore.py
```

You should see output like:
```
🚀 ParkMe Firestore Seeder
========================================
⏳ Seeding parking_spots …
  ✅ parking_spots/A1
  ✅ parking_spots/A2
  ...
⏳ Seeding users …
  ✅ users/abc123  (John Doe)
  ...
🎉 Seeding complete!
```

You can verify in the Firebase Console → Firestore Database — you'll see 4 collections with documents.

---

## Step 7: Run the Backend Locally

```bash
# Make sure you're in Backend/ with venv activated
export GOOGLE_APPLICATION_CREDENTIALS=./serviceAccountKey.json
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

The API is now running at **http://localhost:8000**

- Swagger docs: **http://localhost:8000/docs**
- Web frontend: **http://localhost:8000/** (serves the Frontend/ directory)

---

## Step 8: Deploy to Google Cloud Run

### Option A: Using Cloud Build (CI/CD pipeline)

```bash
# From the Backend/ directory
gcloud builds submit --config cloudbuild.yaml
```

This will:
1. Build the Docker image
2. Push it to Google Container Registry
3. Deploy to Cloud Run in the `me-west1` (Tel Aviv) region

### Option B: Direct deploy from source

```bash
gcloud run deploy parkme-backend \
  --source . \
  --region me-west1 \
  --allow-unauthenticated
```

### Set environment variables on Cloud Run

```bash
gcloud run services update parkme-backend \
  --region me-west1 \
  --set-env-vars "JWT_SECRET=your_production_jwt_secret" \
  --set-env-vars "ENVIRONMENT=production"
```

> **Note:** On Cloud Run, `GOOGLE_APPLICATION_CREDENTIALS` is automatically provided — you don't need to set it or upload `serviceAccountKey.json`. Cloud Run uses the project's default service account.

---

## Step 9: Get Your Backend URL

After deploying, Cloud Run will give you a URL like:

```
https://parkme-backend-XXXXXX-zf.a.run.app
```

This is your backend URL. Update your:
- **Web frontend** — update `app.js` if it has a hardcoded API URL
- **ESP32 sensors** — configure the heartbeat/park endpoints to point here

---

## Step 10: Create Firestore Indexes

The first time you call certain API endpoints, Firestore may return an error like:

```
The query requires an index. You can create it here: https://console.firebase.google.com/...
```

Simply **click the link** in the error message and Firebase will create the index for you. This usually takes 1–2 minutes. You only need to do this once.

---

## Summary Checklist

- [ ] Firebase project created
- [ ] Firestore database enabled
- [ ] `serviceAccountKey.json` downloaded and placed in `Backend/`
- [ ] Google Cloud SDK installed and logged in
- [ ] Google Cloud APIs enabled (Cloud Run, Cloud Build, Container Registry, Firestore)
- [ ] Python venv created and dependencies installed
- [ ] `.env` file configured
- [ ] Database seeded with `python seed_firestore.py`
- [ ] Backend tested locally with `uvicorn`
- [ ] Deployed to Cloud Run
- [ ] Firestore indexes created (via error links on first use)
