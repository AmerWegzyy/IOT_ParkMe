# ParkMe — Run the Backend Locally & Test With Real Hardware

Step-by-step instructions for the local testing phase: flash the boards, run the FastAPI backend on your PC, verify the full pipeline, and then — once everything passes — the exact steps to move the backend to Google Cloud.

> Companion doc: `CLOUD_DEPLOYMENT_GUIDE.md` has the full cloud details, pitfalls, and the complete `SECRETS.h` reference.

---

## Part 1 — Configure `ESP32/SECRETS.h` (already done)

Current values set for local testing:

```c
constexpr char PARKME_WIFI_SSID[]     = "Lina177";
constexpr char PARKME_WIFI_PASSWORD[] = "0545654307";
constexpr char PARKME_SERVER_SCHEME[] = "http";
constexpr char PARKME_SERVER_HOST[]   = "10.0.0.18";   // your PC's WiFi IP
constexpr uint16_t PARKME_SERVER_PORT = 8000;
```

**⚠️ Three things to check before flashing:**

1. **Your PC must be connected to the same WiFi (`Lina177`) as the boards.** The boards talk to the backend by LAN IP — different networks = no connection.
2. **Verify the IP is still `10.0.0.18`** after connecting the PC to Lina177: open PowerShell, run `ipconfig`, look at the *Wireless LAN adapter WiFi* → IPv4 Address. If it differs, update `PARKME_SERVER_HOST` in `SECRETS.h` and re-flash. (Routers can reassign IPs; to make it permanent, reserve the IP for your PC in the router's DHCP settings.)
3. **The WiFi must be 2.4 GHz.** ESP32 cannot see 5 GHz-only networks. If Lina177 is dual-band, that's fine — the boards will use the 2.4 GHz side.

Also confirm (already set correctly in your file):
- `PARKME_GATE_SPOT_ID = "C1"` — matches the seeded Firestore spot
- `PARKME_DISPLAY_ID = "display-c1"` — matches the backend's derived display id for C1
- `PARKME_CAMERA_ESPNOW_PEER_MAC = "24:6F:28:47:F9:E8"` — must be the MAC your camera board prints at boot; if you swapped boards, update it

---

## Part 2 — Flash the Boards (Arduino IDE)

Full details in `ESP32/hardware-upload-guide.md`. Short version:

**Sensor node (standard ESP32):**
1. Open `ESP32/ParkMeSensorNode/ParkMeSensorNode.ino`
2. Tools → Board → **ESP32 Dev Module**, select the COM port
3. Upload (hold BOOT if it hangs on "Connecting...")
4. Open Serial Monitor @ **115200** → note the printed **MAC address**

**Camera node (ESP32-CAM AI-Thinker):**
1. Connect via FTDI, **IO0 → GND** for flash mode, stable 5V
2. Open `ESP32/ParkMeCameraNode/ParkMeCameraNode.ino`
3. Tools → Board → **AI Thinker ESP32-CAM**, select the FTDI COM port
4. Upload, then **disconnect IO0 from GND** and press RESET
5. Serial Monitor @ 115200 → note the printed **MAC address**

**Then make Firestore match the hardware:** the spot document `parking_spots/C1` must have:
- `sensor_mac` = the sensor board's MAC (as printed, e.g. `A0:B7:65:...`)
- `camera_mac` = the camera board's MAC

Edit them in Firebase Console → Firestore, or re-run the seeder after editing the MACs in `Backend/seed_firestore.py`. **If the MACs don't match, the backend silently ignores heartbeats and answers `invalid camera` to uploads.**

---

## Part 3 — Run the Backend Locally

### 3.1 One-time prerequisites

1. **Service account key:** `Backend/serviceAccountKey.json` must exist (Firebase Console → Project Settings → Service Accounts → Generate new private key). Never commit it.
2. **Env file:** `Backend/env` (or `.env`) must contain:
   ```text
   GOOGLE_APPLICATION_CREDENTIALS=./serviceAccountKey.json
   FIREBASE_PROJECT_ID=parkme-technion-f280b
   ENVIRONMENT=development
   ```
3. **Seeded data** (only if the database is empty or you changed MACs):
   ```powershell
   cd Backend
   .venv\Scripts\python.exe seed_firestore.py      # spots A1..C2, users, vehicles
   .venv\Scripts\python.exe create_auth_users.py   # Firebase Auth accounts (password123)
   ```
4. **Windows Firewall:** the boards connect *into* your PC on port 8000, which Windows blocks by default. Allow it once (run PowerShell **as Administrator**):
   ```powershell
   New-NetFirewallRule -DisplayName "ParkMe Backend 8000" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Private
   ```
   (If Lina177 is classified as a Public network, either change it to Private in Windows Settings → WiFi → Lina177 → Network profile, or add `-Profile Any`.)

### 3.2 Start the server

**Easiest — the one-click script (recommended):**
```powershell
Backend\run_local_backend.ps1
```
It creates/uses `Backend\.venv`, installs requirements when they change, and starts uvicorn on **0.0.0.0:8000** (reachable from the LAN) with `--reload`.

**Manual alternative:**
```powershell
cd Backend
.venv\Scripts\activate
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

> ⚠️ **Do not** run plain `uvicorn main:app --reload` — without `--host 0.0.0.0` it binds to 127.0.0.1 only, and the ESP32 boards will get connection refused even though your browser works.

### 3.3 Verify, in this order

| # | Check | Expected |
|---|---|---|
| 1 | Browser → `http://localhost:8000/docs` | FastAPI docs load (server up, credentials OK) |
| 2 | Browser → `http://localhost:8000/` | Dashboard login page; log in as `admin@technion.ac.il` / `password123` |
| 3 | **From your phone's browser** (on Lina177) → `http://10.0.0.18:8000/docs` | Docs load — proves LAN devices can reach the PC (firewall OK). If this fails, the boards will fail too |
| 4 | Power the **sensor node**, watch serial | `Connected. IP: ...` → `POST {...} -> 202` heartbeats → `[SSE] Stream connected.` |
| 5 | Power the **camera node**, watch serial | `WiFi connected` → `Ready for ESP-NOW, Waiting sensor` |
| 6 | Put an object < 20 cm in front of the ultrasonic sensor | Sensor serial: `State: OCCUPIED`, ESP-NOW send `ok`; camera serial: `Taking photo...` → `Photo captured` → `Uploading photo (Attempt 1)` → `HTTP 202`; OLED cycles "Taking photo" → "Photo sent" → server verdict |
| 7 | Admin dashboard | Spot C1 card updates live (plate / UNIDENTIFIED review panel with the photo) |
| 8 | Remove the object | Spot frees; log closes (or "Driver aborted parking" if within 90 s) |

**Uvicorn terminal is your friend:** every heartbeat, upload, OCR result (`[OCR] ... extracted digits`), and SSE connect is logged there.

### Common local problems

| Symptom | Fix |
|---|---|
| Board serial: `Cannot connect to backend` | PC and board on different networks; wrong IP in `SECRETS.h`; firewall (re-check step 3); uvicorn bound to 127.0.0.1 |
| Heartbeat gets 202 but nothing changes in dashboard | `sensor_mac` in Firestore doesn't match the board (backend ignores unknown MACs silently) |
| Upload response: `invalid camera` | `camera_mac` in Firestore doesn't match the camera board |
| Backend crash on start: credentials error | `serviceAccountKey.json` missing or `env` path wrong |
| Every plate becomes UNIDENTIFIED | Vision API not enabled on the project / no billing — check the `[OCR]` log lines |
| WiFi connects then IP changed after router reboot | Re-run `ipconfig`, update `PARKME_SERVER_HOST`, re-flash (or set a DHCP reservation) |

---

## Part 4 — After Local Tests Pass: Move the Backend to the Cloud

Follow these steps **in order**. (Full explanations and 15 troubleshooting entries: `CLOUD_DEPLOYMENT_GUIDE.md`.)

### Step 1 — Code fixes: ✅ already applied

The two former deploy blockers are already fixed in the codebase (July 2026):

1. The static-files mount in `Backend/main.py` is conditional — locally it serves the dashboard, on Cloud Run it runs API-only (Firebase Hosting serves the frontend).
2. `Backend/.dockerignore` exists, keeping `serviceAccountKey.json`, `env`, and `.venv/` out of the container image.

Nothing to do here — continue to Step 2.

### Step 2 — Enable the cloud prerequisites (one-time)

```bash
gcloud auth login
gcloud config set project parkme-technion-f280b
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com vision.googleapis.com firestore.googleapis.com
```
Billing must be enabled, and the Cloud Run runtime service account needs the **Cloud Datastore User** role (IAM page).

### Step 3 — Deploy

```bash
cd Backend
gcloud run deploy parkme-backend `
  --source . `
  --region me-west1 `
  --allow-unauthenticated `
  --timeout=3600 `
  --max-instances=1 `
  --min-instances=1 `
  --memory=512Mi `
  --set-env-vars "ENVIRONMENT=production,FIREBASE_PROJECT_ID=parkme-technion-f280b"
```

Copy the printed **Service URL**, e.g. `https://parkme-backend-abc123-uc.a.run.app`.
Why the flags matter: `--timeout=3600` keeps SSE streams alive; `--max-instances=1` because SSE clients and display commands live in memory; `--min-instances=1` avoids cold starts breaking the camera's 7 s timeout.

Quick check: open `https://<service-url>/docs` — it must load.

### Step 4 — Point the boards at the cloud

Edit `ESP32/SECRETS.h` (only these three lines change from the local setup):

```c
constexpr char PARKME_SERVER_SCHEME[] = "https";
constexpr char PARKME_SERVER_HOST[]   = "parkme-backend-abc123-uc.a.run.app";  // bare hostname: no https://, no slash!
constexpr uint16_t PARKME_SERVER_PORT = 443;
```

Re-flash **both** boards. WiFi settings stay the same — the boards can now be on *any* 2.4 GHz internet-connected WiFi; they no longer need to share a network with your PC.

### Step 5 — Deploy the frontend (Firebase Hosting)

```bash
npm install -g firebase-tools
firebase login
firebase deploy --only hosting        # run from the repo root; public dir = Frontend/
```

Then in `Frontend/app.js`, replace `https://YOUR_CLOUD_RUN_URL/api/v1` with `https://<service-url>/api/v1` and deploy hosting again. Finally, lock down CORS in `main.py`: change `allow_origins=["*"]` to your hosting URL (e.g. `https://parkme-technion-f280b.web.app`) and redeploy the backend.

### Step 6 — Re-run the verification from Part 3.3

Same checklist, but: dashboard at the Firebase Hosting URL, and watch backend logs with:

```bash
gcloud run services logs tail parkme-backend --region me-west1
```

Success = board serial shows `[SSE] Stream connected.` against the Cloud Run host, heartbeats return 202, a parked object flows all the way to the live dashboard, and the OLED shows the server verdict.
