# 🚀 ParkMe — Step-by-Step Cloud Deployment Walkthrough

> **Who is this for?** This guide walks you through **every single action** needed to deploy ParkMe to Google Cloud. Each step includes **what to do**, **the exact command or edit**, and **why you're doing it**.
>
> **Starting point:** You have a working local setup — Firebase project, Firestore, Auth, and Cloud Vision API are already configured.
>
> **End result:** Backend running on **Cloud Run**, frontend on **Firebase Hosting**, ESP32 boards pointing to the cloud.

---

## 📋 Before You Start — Checklist

Make sure you have these ready. If any are missing, fix them first.

| ✅ | Item | How to verify |
|----|------|---------------|
| ☐ | Google Cloud project with **billing enabled** | Go to [Google Cloud Console → Billing](https://console.cloud.google.com/billing) and check that your project `parkme-technion-f280b` has an active billing account |
| ☐ | **gcloud CLI** installed on your computer | Open a terminal and run `gcloud --version`. If it prints a version number, you're good |
| ☐ | **Firebase CLI** installed on your computer | Run `firebase --version` in terminal. If it prints a version, you're good |
| ☐ | Firestore database created (Native mode) | Go to [Firebase Console → Firestore](https://console.firebase.google.com) and confirm you see your collections |
| ☐ | Firebase Auth users seeded | You should have users like `admin@technion.ac.il` already created |
| ☐ | Firestore data seeded (parking spots, vehicles) | You should see `parking_spots` and `vehicles` collections in Firestore |

> [!NOTE]
> If you haven't seeded the data yet, run these from the project root:
> ```bash
> python Backend/seed_firestore.py
> python Backend/create_auth_users.py
> ```

---

## Step 1 — Install & Authenticate the CLI Tools

### 1.1 — Log in to Google Cloud

```bash
gcloud auth login
```

**What happens:** A browser window opens. Sign in with the Google account that owns the `parkme-technion-f280b` project. After login, the terminal confirms you're authenticated.

**Why:** Every `gcloud` command needs to know *who* is running it. This links your terminal session to your Google account.

### 1.2 — Set your default project

```bash
gcloud config set project parkme-technion-f280b
```

**What happens:** This tells `gcloud` that every command from now on should target your ParkMe project, so you don't have to type `--project=parkme-technion-f280b` every time.

**Why:** Without this, commands might accidentally target a different project (or fail asking for one).

### 1.3 — Log in to Firebase

```bash
firebase login
```

**What happens:** Another browser window opens. Sign in with the same Google account. The terminal confirms you're logged in.

**Why:** The `firebase deploy` command later needs this to push your frontend files to Firebase Hosting.

> [!TIP]
> If you've already logged in before, you can skip these login steps. Run `gcloud auth list` and `firebase login --interactive` to check.

---

## Step 2 — Enable Required Google Cloud APIs

```bash
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  vision.googleapis.com \
  firestore.googleapis.com
```

**What happens:** This activates five Google Cloud services on your project. You'll see "Operation finished successfully" for each.

**Why each API matters:**

| API | What it does | Why ParkMe needs it |
|-----|-------------|-------------------|
| `run.googleapis.com` | **Cloud Run** — runs Docker containers | Hosts your Python backend |
| `cloudbuild.googleapis.com` | **Cloud Build** — builds Docker images in the cloud | Converts your `Backend/` code into a container image without needing Docker on your machine |
| `artifactregistry.googleapis.com` | **Artifact Registry** — stores Docker images | Saves the built container image so Cloud Run can pull and run it |
| `vision.googleapis.com` | **Cloud Vision API** — OCR/image analysis | Reads license plates from photos taken by the ESP32 camera |
| `firestore.googleapis.com` | **Firestore API** — NoSQL database | Stores parking spots, vehicles, and user data |

> [!NOTE]
> This is a **one-time** step. If you've already enabled these APIs, running the command again is safe — it just says "already enabled."

---

## Step 3 — Grant Firestore Permissions to Cloud Run

### 3.1 — Find the default service account email

```bash
SA_EMAIL=$(gcloud iam service-accounts list \
  --filter="displayName:Compute Engine default" \
  --format="value(email)")
```

**What happens:** This finds the email address of the default service account that Cloud Run uses. It stores it in a variable called `SA_EMAIL`.

**Why:** Cloud Run runs your backend code *as* this service account. By default, it doesn't have permission to read/write Firestore. We need to grant that.

### 3.2 — Grant the Firestore permission

```bash
gcloud projects add-iam-policy-binding parkme-technion-f280b \
  --member="serviceAccount:$SA_EMAIL" \
  --role="roles/datastore.user"
```

**What happens:** This gives the Cloud Run service account the "Cloud Datastore User" role, which allows it to read and write Firestore documents.

**Why:** Without this, every Firestore operation in your backend will fail with a `403 PERMISSION_DENIED` error.

> [!IMPORTANT]
> You only need to do this **once**. The permission persists until you remove it.

---

## Step 4 — Fix the Backend Code (CRITICAL — Do NOT Skip)

> [!CAUTION]
> **Deploying without these fixes will cause the container to crash on boot AND leak your Firebase private key into the Docker image.** Both fixes are mandatory.

### 4.1 — Fix the frontend static files crash

**File to edit:** `Backend/main.py` (around lines 1607–1608)

**Find this code:**

```python
frontend_dir = os.path.join(os.path.dirname(__file__), "../Frontend")
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
```

**Replace it with:**

```python
frontend_dir = os.path.join(os.path.dirname(__file__), "../Frontend")
if os.path.isdir(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
```

**Why this matters:**
- When running locally, `../Frontend` exists (it's right there in your project) → the dashboard gets served. ✅
- In the Docker container, only `Backend/` is copied. `../Frontend` doesn't exist inside the container → FastAPI tries to mount a non-existent folder → **crashes immediately** → Cloud Run shows "failed to start and listen on PORT." ❌
- The `if os.path.isdir(...)` check makes it skip the mount when the folder is missing. The frontend will be served separately from Firebase Hosting instead.

### 4.2 — Create Backend/.dockerignore to prevent secret leaks

**File to create:** `Backend/.dockerignore` (this file does NOT exist yet — create it)

**Content:**

```text
serviceAccountKey.json
env
.env
.venv/
venv/
__pycache__/
*.pyc
run_local_backend.ps1
```

**Why this matters:**
- The Dockerfile has `COPY . .` which copies **everything** in `Backend/` into the Docker image.
- Without `.dockerignore`, this includes:
  - `serviceAccountKey.json` — your Firebase Admin SDK **private key**. Anyone who pulls the image can extract it and get full admin access to your Firebase project. 🚨
  - `.env` / `env` — contains `GOOGLE_APPLICATION_CREDENTIALS=./serviceAccountKey.json` which overrides the correct cloud authentication and causes credential errors.
  - `venv/` — hundreds of MB of local Python packages that bloat the image for no reason.
- The `.dockerignore` file tells Docker to skip these files during `COPY`.

> [!WARNING]
> The root-level `.dockerignore` file does NOT apply here. When you build from `Backend/` as the build context, Docker only looks for `.dockerignore` inside `Backend/`.

---

## Step 5 — Deploy the Backend to Cloud Run

### 5.1 — Run the deploy command

Navigate to the Backend directory and deploy:

```bash
cd Backend

gcloud run deploy parkme-backend \
  --source . \
  --region me-west1 \
  --allow-unauthenticated \
  --timeout=3600 \
  --max-instances=1 \
  --min-instances=1 \
  --memory=512Mi \
  --set-env-vars "ENVIRONMENT=production,FIREBASE_PROJECT_ID=parkme-technion-f280b"
```

**What happens:** Google Cloud will:
1. Upload your `Backend/` source code to Cloud Build
2. Build a Docker image from your `Dockerfile`
3. Push the image to Artifact Registry
4. Deploy it as a Cloud Run service named `parkme-backend`
5. Print the service URL when done

This takes **3–8 minutes**. Be patient.

**Why each flag matters:**

| Flag | What it does | Why you need it |
|------|-------------|-----------------|
| `--source .` | Build from current directory | Uses your `Dockerfile` in `Backend/` |
| `--region me-west1` | Deploy to Tel Aviv data center | Low latency for Israel-based users and ESP32 boards |
| `--allow-unauthenticated` | Allow anyone to call the API | ESP32 boards and the public dashboard can't do Google IAM auth. Your app uses Firebase JWT tokens for user auth instead |
| `--timeout=3600` | Set request timeout to 1 hour | SSE (Server-Sent Events) connections are long-lived. The default 5-minute timeout would kill every dashboard/sensor stream every 5 minutes |
| `--max-instances=1` | Only ever run 1 container | Your backend stores SSE client lists and display commands **in memory**. With 2+ instances, a dashboard on instance A would never see events from a sensor on instance B |
| `--min-instances=1` | Always keep 1 container running | Prevents "cold starts" (5–15 seconds to boot). The ESP32 camera has a 7-second HTTP timeout — it would fail on cold starts. Also prevents losing in-memory SSE state |
| `--memory=512Mi` | Give the container 512 MB of RAM | Enough for Vision API image processing |
| `--set-env-vars ...` | Set environment variables | `FIREBASE_PROJECT_ID` is needed by the backend to verify Firebase JWT tokens. Without it, `auth.verify_id_token` fails with an audience mismatch error |

### 5.2 — Copy the Cloud Run URL

When the deployment finishes, you'll see output like:

```
Service URL: https://parkme-backend-XXXXXXXXXX-zf.a.run.app
```

**⚡ Copy this URL and save it somewhere.** You'll need it in the next steps.

If you lose it, you can always get it back with:

```bash
gcloud run services describe parkme-backend --region me-west1 --format="value(status.url)"
```

### 5.3 — Quick test — Is the backend alive?

```bash
curl https://parkme-backend-XXXXXXXXXX-zf.a.run.app/docs
```

Replace `XXXXXXXXXX` with your actual URL hash. If you see HTML with "FastAPI" in it, the backend is running! 🎉

---

## Step 6 — Update the Frontend API URL

### 6.1 — Edit `Frontend/app.js` (line 9)

**Find this line:**

```javascript
        ? 'https://YOUR_CLOUD_RUN_URL/api/v1'
```

**Replace `YOUR_CLOUD_RUN_URL` with your actual Cloud Run URL:**

```javascript
        ? 'https://parkme-backend-XXXXXXXXXX-zf.a.run.app/api/v1'
```

**Why:** When the frontend is hosted on Firebase (`*.web.app`), it can't reach `localhost:8000` anymore. It needs the public Cloud Run URL to make API calls and open SSE streams.

> [!IMPORTANT]
> Keep the `/api/v1` suffix — that's the API base path. Only replace the `YOUR_CLOUD_RUN_URL` part.

---

## Step 7 — Set the Firebase Project ID

### 7.1 — Edit `.firebaserc` (in the project root)

**Find this content:**

```json
{
  "projects": {
    "default": "YOUR_FIREBASE_PROJECT_ID"
  }
}
```

**Replace it with:**

```json
{
  "projects": {
    "default": "parkme-technion-f280b"
  }
}
```

**Why:** The Firebase CLI reads this file to know *which Firebase project* to deploy to. Without the correct project ID, `firebase deploy` will either fail or deploy to the wrong project.

---

## Step 8 — Deploy the Frontend to Firebase Hosting

### 8.1 — Run the deploy command

From the **project root** directory (not from `Backend/` or `Frontend/`):

```bash
cd /path/to/IOT_ParkMe
firebase deploy --only hosting
```

**What happens:** Firebase CLI:
1. Reads `firebase.json` to know which folder to deploy (should point to `Frontend/`)
2. Uploads all frontend files (HTML, CSS, JS) to Firebase Hosting's global CDN
3. Makes them available at public URLs

**After it finishes, your frontend is live at:**
- `https://parkme-technion-f280b.web.app`
- `https://parkme-technion-f280b.firebaseapp.com`

### 8.2 — Quick test — Does the frontend load?

Open `https://parkme-technion-f280b.web.app` in your browser. You should see the ParkMe login page.

Try logging in with:
- **Email:** `admin@technion.ac.il`
- **Password:** `password123`

If the dashboard loads and you see a green connection dot in the header → everything is connected! 🎉

---

## Step 9 — Update ESP32 Firmware

### 9.1 — Edit `ESP32/SECRETS.h`

Open the file and update these values:

```cpp
// ===== WiFi =====
constexpr char PARKME_WIFI_SSID[]     = "YourWiFiName";      // ⚠️ Must be 2.4 GHz!
constexpr char PARKME_WIFI_PASSWORD[]  = "YourWiFiPassword";

// ===== Cloud Run Server =====
constexpr char PARKME_SERVER_SCHEME[]  = "https";
constexpr char PARKME_SERVER_HOST[]    = "parkme-backend-XXXXXXXXXX-zf.a.run.app";  // ← Your URL, bare hostname only!
constexpr uint16_t PARKME_SERVER_PORT  = 443;
```

**Key things to get right:**

| Setting | Correct ✅ | Wrong ❌ | Why |
|---------|-----------|---------|-----|
| `PARKME_SERVER_HOST` | `parkme-backend-xxx-zf.a.run.app` | `https://parkme-backend-xxx-zf.a.run.app` | No `https://` prefix — just the hostname |
| `PARKME_SERVER_HOST` | `parkme-backend-xxx-zf.a.run.app` | `parkme-backend-xxx-zf.a.run.app/` | No trailing slash |
| `PARKME_SERVER_PORT` | `443` | `8000` | Cloud Run uses HTTPS on port 443, not your local port |
| `PARKME_WIFI_SSID` | A 2.4 GHz network | A 5 GHz or enterprise WPA2 network | ESP32 only supports 2.4 GHz. Campus eduroam won't work — use a phone hotspot |

### 9.2 — Verify spot IDs match Firestore

Make sure these match your Firestore `parking_spots` documents **exactly** (case-sensitive):

```cpp
constexpr char PARKME_GATE_SPOT_ID[]  = "C1";          // Must match a parking_spots document ID
constexpr char PARKME_DISPLAY_ID[]    = "display-c1";   // Must match the spot's display_id field
```

### 9.3 — Flash both ESP32 boards

Upload the updated firmware to **both** the sensor board and the camera board using Arduino IDE or PlatformIO.

### 9.4 — Check serial monitor output

Open the serial monitor at **115200 baud** for each board. Look for:

**Sensor board — should show:**
```
WiFi connected! IP: 192.168.x.x
MAC: AA:BB:CC:DD:EE:FF
Backend: https://parkme-backend-xxx-zf.a.run.app:443
[SSE] Stream connected.
```

**Camera board — should show:**
```
WiFi connected! IP: 192.168.x.x
MAC: 11:22:33:44:55:66
Gate spot: C1
```

### 9.5 — Update MAC addresses in Firestore

The MAC addresses printed in the serial output need to be saved in Firestore:

1. Go to [Firebase Console → Firestore](https://console.firebase.google.com)
2. Navigate to the `parking_spots` collection → your spot document (e.g., `C1`)
3. Set the `sensor_mac` field to the sensor board's MAC address
4. Set the `camera_mac` field to the camera board's MAC address

**Why:** The backend uses MAC addresses to identify which board is sending data. If the MACs don't match, sensor heartbeats and camera uploads will be silently ignored.

---

## Step 10 — Verify Everything Works End-to-End

Run through this checklist to confirm the full system is working:

| # | What to test | How | What you should see |
|---|-------------|-----|-------------------|
| 1 | Backend is alive | Run: `curl https://<your-url>/docs` | HTML page with "FastAPI" loads |
| 2 | Display poll endpoint | Run: `curl -X POST https://<your-url>/api/v1/displays/poll -H "Content-Type: application/json" -d '{"display_id":"display-c1"}'` | Response: `{"action":"IDLE"}` |
| 3 | Frontend loads | Open `https://parkme-technion-f280b.web.app` in browser | Login page appears |
| 4 | Login works | Enter `admin@technion.ac.il` / `password123` | Dashboard loads |
| 5 | SSE is connected | Look at the header bar in the dashboard | Green dot = connected ✅ |
| 6 | No errors in logs | Run: `gcloud run logs read parkme-backend --region me-west1 --limit 50` | No Vision API or Firestore errors |
| 7 | Sensor connects | Power on the sensor board | Serial: `[SSE] Stream connected.` and heartbeat `-> 202` |
| 8 | Camera works | Trigger a camera capture | License plate recognized, parking spot updated |

---

## Step 11 (Optional) — Tighten Security

After you've confirmed everything works, lock down CORS so only your frontend can call the API:

**Edit `Backend/main.py` (around line 81):**

```python
# Change from:
allow_origins=["*"],

# Change to:
allow_origins=["https://parkme-technion-f280b.web.app", "https://parkme-technion-f280b.firebaseapp.com"],
```

Then redeploy the backend:

```bash
cd Backend
gcloud run deploy parkme-backend \
  --source . \
  --region me-west1 \
  --allow-unauthenticated \
  --timeout=3600 \
  --max-instances=1 \
  --min-instances=1 \
  --memory=512Mi \
  --set-env-vars "ENVIRONMENT=production,FIREBASE_PROJECT_ID=parkme-technion-f280b"
```

**Why:** `allow_origins=["*"]` means any website can make API calls to your backend. Restricting it to your Firebase Hosting domains prevents other sites from abusing your API.

---

## 🔧 Troubleshooting — If Something Goes Wrong

### How to view backend logs

```bash
# See the last 50 log entries
gcloud run logs read parkme-backend --region me-west1 --limit 50

# Live-stream logs (useful while testing)
gcloud run logs tail parkme-backend --region me-west1
```

### Common problems and fixes

| Problem | What you see | Cause | Fix |
|---------|-------------|-------|-----|
| Container won't start | Cloud Run: "failed to start and listen on PORT" | Missing `if os.path.isdir()` check in `main.py` | Go back to Step 4.1 |
| Credential crash | Logs: `DefaultCredentialsError` | `.env` file baked into image | Go back to Step 4.2 — check `.dockerignore` exists |
| Dashboard never updates | Green dot but no live changes | Multiple container instances | Redeploy with `--max-instances=1` |
| Streams disconnect every 5 min | Dashboard/LCD hiccups regularly | 300s default timeout | Redeploy with `--timeout=3600` |
| Camera timeout on first request | 10+ seconds to respond after idle | Cold start (no warm instances) | Redeploy with `--min-instances=1` |
| Photos always "UNIDENTIFIED" | OCR worked locally, fails in cloud | Vision API not enabled or billing off | Run Step 2 again; check billing |
| Firestore permission denied | Logs: `403 PERMISSION_DENIED` | Service account missing role | Go back to Step 3 |
| Login fails with 401 | `/users/me` returns unauthorized | Wrong `FIREBASE_PROJECT_ID` env var | Check `--set-env-vars` in deploy command |
| ESP32 can't connect | No network connection | 5 GHz WiFi, or `HOST` has `https://` prefix | Check Step 9.1 table |
| Spot never updates after capture | Camera uploads succeed (200) but spot unchanged | `camera_mac` doesn't match Firestore | Go back to Step 9.5 |

---

## 💰 Expected Costs

| Service | Free Tier Limit | Your Expected Usage | Monthly Cost |
|---------|----------------|-------------------|-------------|
| Cloud Run (requests) | 2M requests/month | ~50K | **$0** |
| Cloud Run (min-instance) | Not included in free tier | 1 instance × 512 MB idle | **~$3–5** |
| Firestore | 50K reads/day | ~10K | **$0** |
| Cloud Vision | 1,000 units/month | ~200 | **$0** |
| Firebase Hosting | 10 GB, 360 MB/day | ~50 MB | **$0** |
| Firebase Auth | 50K monthly active users | ~10 users | **$0** |
| Cloud Build | 120 min/day | ~5 builds | **$0** |
| | | **Total** | **~$3–5/month** |

> [!NOTE]
> The `--min-instances=1` is the only thing that costs money. It's the price of reliable SSE streams and no cold-start camera timeouts. Without it, everything is free but SSE/display connections will break whenever Cloud Run scales to zero.

---

## 📌 Quick Reference — Deployment Order Summary

```
1. Login           → gcloud auth login + firebase login
2. Enable APIs     → gcloud services enable ...
3. IAM permission  → Grant datastore.user role
4. Code fixes      → main.py conditional mount + .dockerignore
5. Deploy backend  → gcloud run deploy ... → COPY THE URL
6. Update app.js   → Paste Cloud Run URL
7. Set .firebaserc → Set project ID
8. Deploy frontend → firebase deploy --only hosting
9. Update ESP32    → Edit SECRETS.h → flash boards → update MACs in Firestore
10. Verify         → Run through the checklist
```

---

## 🔁 Future Redeployments

After making code changes, here's how to redeploy each component:

**Backend only:**
```bash
cd Backend
gcloud run deploy parkme-backend --source . --region me-west1 --allow-unauthenticated \
  --timeout=3600 --max-instances=1 --min-instances=1 --memory=512Mi \
  --set-env-vars "ENVIRONMENT=production,FIREBASE_PROJECT_ID=parkme-technion-f280b"
```

**Frontend only:**
```bash
firebase deploy --only hosting
```

**Get current Cloud Run URL:**
```bash
gcloud run services describe parkme-backend --region me-west1 --format="value(status.url)"
```

**View logs:**
```bash
gcloud run logs read parkme-backend --region me-west1 --limit 50
```

---

*ParkMe — ICST, Technion. July 2026.*
