# ☁️ ParkMe Cloud — Complete Guide for the Team

> **Your project is deployed.** This guide covers everything you and your friend need to know: updating the ESP32 boards, how long things stay running, and what to do when the project is over.

---

## 📍 Your Live URLs

| Service | URL |
|---------|-----|
| **Frontend (Dashboard)** | https://parkme-technion-f280b.web.app |
| **Backend (API)** | https://parkme-backend-31114651685.me-west1.run.app |
| **API Docs** | https://parkme-backend-31114651685.me-west1.run.app/docs |

---

## Part 1 — Updating ESP32 to Send to the Real Cloud URL

### What to change in `ESP32/SECRETS.h`

Open `ESP32/SECRETS.h` and update these 3 lines:

```diff
- constexpr char PARKME_SERVER_SCHEME[] = "http";
+ constexpr char PARKME_SERVER_SCHEME[] = "https";

- constexpr char PARKME_SERVER_HOST[] = "";
+ constexpr char PARKME_SERVER_HOST[] = "parkme-backend-31114651685.me-west1.run.app";

- constexpr uint16_t PARKME_SERVER_PORT = 8000;
+ constexpr uint16_t PARKME_SERVER_PORT = 443;
```

Also update the WiFi to a **2.4 GHz network** (ESP32 doesn't support 5 GHz):

```diff
- constexpr char PARKME_WIFI_SSID[] = "Hazim";
- constexpr char PARKME_WIFI_PASSWORD[] = "";
+ constexpr char PARKME_WIFI_SSID[] = "YourWiFiName";
+ constexpr char PARKME_WIFI_PASSWORD[] = "YourWiFiPassword";
```

> ⚠️ **Campus WiFi (eduroam) won't work** — use a phone hotspot instead.

### ❌ Common mistakes to avoid

| Wrong ❌ | Right ✅ | Why |
|---------|---------|-----|
| `"https://parkme-backend-31114651685.me-west1.run.app"` | `"parkme-backend-31114651685.me-west1.run.app"` | No `https://` prefix — bare hostname only |
| `"parkme-backend-31114651685.me-west1.run.app/"` | `"parkme-backend-31114651685.me-west1.run.app"` | No trailing slash |
| Port `8000` | Port `443` | Cloud Run uses HTTPS port 443 |
| `"http"` | `"https"` | Cloud Run is HTTPS only |

### ❗ Don't touch these lines — leave them as-is

```cpp
constexpr char PARKME_API_UPDATE_SPOT_PATH[] = "/api/v1/sensors/heartbeat";
constexpr char PARKME_API_GATE_ENTRY_PATH[]  = "/api/v1/sensors/park";
constexpr char PARKME_API_DISPLAY_POLL_PATH[] = "/api/v1/displays/poll";
constexpr char PARKME_API_DISPLAY_RESULT_PATH[] = "/api/v1/displays/result";
```

These API paths match the backend and don't change between local and cloud.

### After editing SECRETS.h

1. **Flash both boards** (sensor + camera) using Arduino IDE or PlatformIO
2. **Open Serial Monitor** at 115200 baud
3. **Look for these messages:**

**Sensor board:**
```
WiFi connected! IP: 192.168.x.x
MAC: AA:BB:CC:DD:EE:FF
Backend: https://parkme-backend-31114651685.me-west1.run.app:443
[SSE] Stream connected.
```

**Camera board:**
```
WiFi connected! IP: 192.168.x.x
MAC: 11:22:33:44:55:66
Gate spot: C1
```

4. **Update Firestore with the MAC addresses:**
   - Go to [Firebase Console → Firestore](https://console.firebase.google.com/project/parkme-technion-f280b/firestore)
   - Navigate to `parking_spots` → your spot doc (e.g., `C1`)
   - Set `sensor_mac` = the sensor board's MAC (from serial output)
   - Set `camera_mac` = the camera board's MAC (from serial output)

---

## Part 2 — How Long Does Everything Keep Running?

### Short answer: It runs on Google's servers, not on your computer.

**Closing PyCharm, shutting down your laptop, or turning off your PC changes nothing.** The cloud services are completely independent of your machine.

### Frontend (Firebase Hosting)

| Question | Answer |
|----------|--------|
| How long does it run? | **Forever** — until you delete it |
| Does it cost money? | **No** — free tier |
| Can it go down? | No — it's static files on Google's global CDN |
| Same URL forever? | **Yes** — `parkme-technion-f280b.web.app` never changes |

### Backend (Cloud Run)

| Question | Answer |
|----------|--------|
| How long does it run? | **As long as billing is active** (your $50 coupon) |
| Does it cost money? | **~$3–5/month** (with `min-instances=1`) |
| Does it go down if I close PyCharm? | **No** — it runs on Google's servers |
| Does it go down if I turn off my laptop? | **No** |
| Same URL forever? | **Yes** — `parkme-backend-31114651685.me-west1.run.app` never changes |
| What if the $50 coupon runs out? | Services stop (but nothing is deleted). Add credit or switch to `min-instances=0` |

### Think of it like this:

```
BEFORE (local):    Your laptop runs the backend → laptop off = everything stops
AFTER (cloud):     Google's servers run the backend → your laptop doesn't matter
```

Your laptop is now only needed to:
- Edit and push code changes
- Flash ESP32 boards
- Redeploy (if you change code)

---

## Part 3 — When the Project is Over (Cleanup Steps)

When your course/project is finished and you no longer need ParkMe running, follow these steps to **avoid surprise charges** after the coupon expires.

### Option A — Delete everything (recommended when fully done)

#### Step 1: Delete the Cloud Run service
```bash
gcloud run services delete parkme-backend --region me-west1
```
This stops the backend and removes all charges.

#### Step 2: Delete the frontend hosting
```bash
firebase hosting:disable --project parkme-technion-f280b
```
This takes down the website.

#### Step 3: Delete the Artifact Registry images (saves storage)
```bash
gcloud artifacts repositories delete cloud-run-source-deploy \
  --location=me-west1 --quiet
```

#### Step 4: (Optional) Delete the entire Google Cloud project
If you want to remove **everything** at once (Firestore data, Auth users, all services):
```bash
gcloud projects delete parkme-technion-f280b
```
> ⚠️ This is **irreversible** — all data is permanently deleted after 30 days.

### Option B — Just stop paying (minimum effort)

If you're lazy and just want to stop charges:

```bash
gcloud run services update parkme-backend --region me-west1 --min-instances=0
```

This makes the backend scale to zero when idle → **$0/month**. Everything stays deployed but the backend sleeps when nobody uses it. When the coupon eventually expires and there's no spending, nothing bad happens.

### Summary: What costs money and what doesn't

| Service | Costs money? | How to stop cost |
|---------|-------------|-----------------|
| Cloud Run (`min-instances=1`) | **~$3–5/month** | Set to `min-instances=0` or delete |
| Cloud Run (`min-instances=0`) | **$0** | Nothing needed |
| Firebase Hosting | **$0** | Nothing needed |
| Firestore | **$0** (free tier) | Nothing needed |
| Firebase Auth | **$0** (free tier) | Nothing needed |
| Cloud Vision API | **$0** (free tier) | Nothing needed |

---

## Part 4 — Quick Reference Commands

### Redeploy after code changes

**Backend:**
```bash
cd Backend
gcloud run deploy parkme-backend --source . --region me-west1 --allow-unauthenticated \
  --timeout=3600 --max-instances=1 --min-instances=1 --memory=512Mi \
  --set-env-vars "ENVIRONMENT=production,FIREBASE_PROJECT_ID=parkme-technion-f280b"
```

**Frontend:**
```bash
firebase deploy --only hosting
```

### Switch between free and always-on

```bash
# Always-on (no cold starts, ~$3-5/month from coupon)
gcloud run services update parkme-backend --region me-west1 --min-instances=1

# Free (cold starts after idle, $0/month)
gcloud run services update parkme-backend --region me-west1 --min-instances=0
```

### View backend logs

```bash
# Last 50 log entries
gcloud run logs read parkme-backend --region me-west1 --limit 50

# Live stream (Ctrl+C to stop)
gcloud run logs tail parkme-backend --region me-west1
```

### Get the Cloud Run URL

```bash
gcloud run services describe parkme-backend --region me-west1 --format="value(status.url)"
```

---

## Part 5 — For Your Friend (Quick Setup)

If your friend wants to work on the code:

### 1. Clone the repo
```bash
git clone https://github.com/AmerWegzyy/IOT_ParkMe.git
cd IOT_ParkMe
```

### 2. Get the secret files from you (NOT in git)
You need to send these privately (WhatsApp, USB, etc.):

| File | Put it in |
|------|-----------|
| `serviceAccountKey.json` | `Backend/` |
| `env` or `.env` | `Backend/` |

### 3. Install Python and run locally (optional)
```bash
cd Backend
python -m venv venv
source venv/bin/activate      # Mac/Linux
# venv\Scripts\activate       # Windows
pip install -r requirements.txt
python main.py
```
Open `http://localhost:8000`

### 4. To deploy changes to the cloud
They need `gcloud` and `firebase` CLI installed + their Google account needs project access:
- Ask Amir to add them at [IAM page](https://console.cloud.google.com/iam-admin/iam?project=parkme-technion-f280b) → Grant Access → role: **Editor**

---

*ParkMe — ICST, Technion. July 2026.*
