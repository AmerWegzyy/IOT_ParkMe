# ParkMe — Google Cloud Deployment Guide

Everything required to deploy the FastAPI backend to **Google Cloud Run**, the problems you will (not just might) run into with the current code, and the exact `SECRETS.h` checklist for pointing the ESP32 boards at the deployed backend.

> Verified against the actual code on `camera_buffer_fix_branch` (July 2026). Project: `parkme-technion-f280b`, region `me-west1` (Tel Aviv).

---

## 1. Prerequisites

| What | Why | How to check |
|---|---|---|
| Google Cloud project with **billing enabled** | Cloud Run, Cloud Build, and Vision API all require it | Console → Billing |
| **gcloud CLI** installed & authenticated | All deploy commands | `gcloud auth login` then `gcloud config set project parkme-technion-f280b` |
| **APIs enabled**: Cloud Run, Cloud Build, Artifact Registry, Cloud Vision, Firestore | Backend calls Vision + Firestore; deploy uses Run/Build | `gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com vision.googleapis.com firestore.googleapis.com` |
| Firestore database created (Native mode) | Sole datastore | Firebase Console → Firestore |
| Firebase Auth users + Firestore seeded | Login and spot/vehicle lookups | `python Backend/seed_firestore.py` and `python Backend/create_auth_users.py` |
| Service account permissions | The Cloud Run runtime service account (default: Compute Engine default SA) needs **Cloud Datastore User** (`roles/datastore.user`) for Firestore. Vision needs no special role once the API is enabled. | IAM page |

Notes:
- In production the backend uses **Application Default Credentials (ADC)** — `credentials.ApplicationDefault()` in `main.py` — so **no service account key file is needed or wanted** inside the container.
- Firebase ID-token verification (`auth.verify_id_token`) uses Google's public certificates; no extra IAM role required.

---

## 2. Code Fixes — ✅ ALREADY APPLIED (July 2026)

The four deployment blockers below have **already been fixed in the codebase**. This section is kept as context so you understand *why* the code and deploy flags look the way they do — no action is needed.

### 2.1 ✅ Fixed: container crash on boot (`Frontend/` outside the build context)

When the image is built from `Backend/`, `../Frontend` does not exist inside the container, and an unconditional `StaticFiles` mount would raise at import time → "failed to start and listen on PORT".

**Applied fix** (bottom of `Backend/main.py`): the mount is now conditional —

```python
frontend_dir = os.path.join(os.path.dirname(__file__), "../Frontend")
if os.path.isdir(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
else:
    logger.info("Frontend directory not found; running API-only (cloud mode).")
```

Local runs still serve the dashboard at `/`; on Cloud Run the backend runs API-only and **Firebase Hosting serves the frontend**.

### 2.2 ✅ Fixed: secrets baked into the image

The root `.dockerignore` does not apply when the build context is `Backend/`, so `COPY . .` used to copy `serviceAccountKey.json` (the Firebase admin private key!), the `env` file (whose `GOOGLE_APPLICATION_CREDENTIALS` line would override ADC in production and crash the service), and the multi-hundred-MB `.venv/`.

**Applied fix:** `Backend/.dockerignore` now exists and excludes `serviceAccountKey.json`, `env`, `.env`, `.venv/`, `__pycache__/`, and other local-only files. In the cloud the backend authenticates via Application Default Credentials — no key file needed.

### 2.3 ✅ Handled: in-memory state means exactly ONE instance

`sse_clients`, `display_sse_clients`, and `display_command_store` live in process memory — with autoscaling, a dashboard could connect its SSE stream to instance A while events are generated on instance B and never arrive.

**Applied fix:** both the deploy command in §3 **and** `Backend/cloudbuild.yaml` now pin `--max-instances=1` and keep `--min-instances=1` (so the command store isn't wiped by scale-to-zero, and cold starts don't break the camera's 7 s HTTP timeout).

### 2.4 ✅ Handled: SSE streams need a long request timeout

Cloud Run's default 300 s request timeout would kill every SSE connection (dashboard + sensor nodes) every 5 minutes. Clients auto-reconnect, but the hiccup is visible.

**Applied fix:** `--timeout=3600` is included in the §3 deploy command and in `Backend/cloudbuild.yaml`.

---

## 3. Deploy Commands

The code is deploy-ready (§2 fixes are already in). Just run:

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

Flag rationale:
- `--allow-unauthenticated` — the ESP32 boards and the public dashboard cannot do IAM auth. App-level auth (Firebase JWT) protects the user endpoints; hardware endpoints are MAC-identified by design.
- `--set-env-vars FIREBASE_PROJECT_ID=…` — `main.py` reads it to initialize firebase-admin.
- `--timeout / --max-instances / --min-instances` — see §2.3–2.4.
- The `Dockerfile` already honors Cloud Run's injected `$PORT` (`CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}`).

Alternatively, the CI pipeline: `gcloud builds submit --config cloudbuild.yaml .` from `Backend/` (build → push to GCR → deploy). `cloudbuild.yaml` has been updated to include the same timeout/instance/memory flags and env vars as the command above, so both paths produce an identical configuration.

### Deploying the frontend (Firebase Hosting)

```bash
npm install -g firebase-tools
firebase login
firebase deploy --only hosting     # public dir is Frontend/ per firebase.json
```

Then edit `Frontend/app.js`: replace the `https://YOUR_CLOUD_RUN_URL/api/v1` placeholder with the real Cloud Run URL (e.g. `https://parkme-backend-xxxxx-uc.a.run.app/api/v1`) and redeploy hosting. Finally, tighten CORS in `main.py` from `allow_origins=["*"]` to your hosting origin.

### Post-deploy verification checklist

1. `curl https://<service-url>/docs` → FastAPI docs page loads (service booted).
2. `curl -X POST https://<service-url>/api/v1/displays/poll -H "Content-Type: application/json" -d '{"display_id":"display-c1"}'` → `{"action":"IDLE"}`.
3. Log in on the dashboard → spots render, connection dot turns green (SSE connected).
4. `gcloud run services logs read parkme-backend --region me-west1` → no credential or Vision errors.
5. Power a sensor node with updated `SECRETS.h` → its serial monitor shows `[SSE] Stream connected.` and heartbeat `-> 202` responses.

---

## 4. Problems You Might Run Into (symptom → cause → fix)

| # | Symptom | Cause | Fix |
|---|---|---|---|
| 1 | Container fails: "failed to start and listen on PORT" | Should no longer happen — fixed by the conditional `StaticFiles` mount (§2.1). If it reappears, someone reverted that change in `main.py` | Restore the conditional mount |
| 2 | Crash loop: `DefaultCredentialsError` | Should no longer happen — `Backend/.dockerignore` (§2.2) keeps `env`/key out of the image. If it reappears, the `.dockerignore` was deleted or renamed | Restore `Backend/.dockerignore`; rely on ADC |
| 3 | Dashboard connects but never updates | Deployed without `--max-instances=1` (§2.3) — e.g. a hand-typed deploy command missing the flags | Redeploy with the full §3 command (or `cloudbuild.yaml`, which includes them) |
| 4 | Dashboard/LCD hiccup exactly every 5 min | Deployed without `--timeout=3600` (§2.4) | Same as #3 |
| 5 | First request after idle takes 10+ s; camera logs "Backend response timeout" | Deployed without `--min-instances=1`, or it was set to 0 to save credits and not restored | `gcloud run services update parkme-backend --region me-west1 --min-instances=1` |
| 6 | Every photo becomes UNIDENTIFIED in cloud but OCR worked locally | Vision API not enabled on the project, or billing disabled | Enable `vision.googleapis.com` + billing; check logs for `[OCR] Failed` |
| 7 | `403 PERMISSION_DENIED` on Firestore in logs | Runtime service account missing `roles/datastore.user` | Grant it in IAM |
| 8 | Login works but `/users/me` returns 401 "Invalid or expired Firebase token" | Wrong `FIREBASE_PROJECT_ID` env var (token audience mismatch), or > 10 s clock skew | Set the env var correctly; skew is configurable via `FIREBASE_CLOCK_SKEW_SECONDS` |
| 9 | ESP32 can't connect at all | Board on a 5 GHz-only network (ESP32 is 2.4 GHz only); or `PARKME_SERVER_HOST` contains `https://` prefix or a path (it must be the bare hostname); or port ≠ 443 | Fix `SECRETS.h` (see §5); use a 2.4 GHz SSID/hotspot |
| 10 | ESP32 TLS handshake failures / out of memory | Large TLS cert chains; the code already uses `setInsecure()` (no verification) which avoids CA storage — but each `WiFiClientSecure` handshake still costs ~40 KB heap | Normal on Cloud Run; if heap-starved on the CAM, reduce concurrent connections (the code already opens one at a time) |
| 11 | Camera uploads return 200 but spot never updates | `camera_mac` doesn't match any `parking_spots` doc — response is `invalid camera` with HTTP 202 | Copy the exact MAC from the camera's boot serial into the spot document (`camera_mac` field) |
| 12 | Display never shows server messages | `display_id` mismatch: backend derives `display-<spot_id lowercase>` unless the spot doc has an explicit `display_id`; `SECRETS.h` must match | Align `PARKME_DISPLAY_ID` with the spot doc / derived ID |
| 13 | Old dashboard tab stops updating after redeploy | Redeploy killed the SSE connection and the token may have expired (Firebase ID tokens last 1 h) | Frontend auto-reconnects; re-login if token expired |
| 14 | Surprise Vision API bill | Each park event = up to 2 Vision calls (`text_detection` + fallback) | Free tier is 1,000 units/feature/month; fine for testing, watch it for demos with many triggers |
| 15 | `me-west1` not offered for some feature | Newer region with occasional service gaps | Fall back to `europe-west1`; update ESP32/latency expectations |

Costs at course scale: Cloud Run free tier covers this easily **except** `--min-instances=1`, which bills idle time (~a few $/month for 512 Mi) — the price of reliable SSE.

---

## 5. `ESP32/SECRETS.h` Checklist

Copy `ESP32/SECRETS.example.h` → `ESP32/SECRETS.h` (git-ignored — **never commit it**). Both sketches include it via `ParkMeConfig.h`. What each deployment-relevant value must be:

### Must change for cloud deployment

| Constant | Set to | Gotchas |
|---|---|---|
| `PARKME_WIFI_SSID` / `PARKME_WIFI_PASSWORD` | Your WiFi or phone hotspot | **2.4 GHz only.** Campus enterprise WPA2 (802.1X) won't work — use a hotspot |
| `PARKME_SERVER_SCHEME` | `"https"` | Cloud Run is HTTPS-only |
| `PARKME_SERVER_HOST` | e.g. `"parkme-backend-xxxxx-uc.a.run.app"` | **Bare hostname only** — no `https://`, no trailing `/`, no path. It goes into `client->connect(host, port)` and the `Host:` header verbatim |
| `PARKME_SERVER_PORT` | `443` | With scheme+443 the URL builder omits the port correctly |

### Must match the Firestore data

| Constant | Set to | Gotchas |
|---|---|---|
| `PARKME_GATE_SPOT_ID` | e.g. `"C1"` | Must equal a `parking_spots` **document ID** exactly (case-sensitive). Used by the sensor in ESP-NOW messages and printed at boot |
| `PARKME_DISPLAY_ID` | e.g. `"display-c1"` | Must equal the spot doc's `display_id` field, or the derived default `display-<spot_id lowercase>`. Backend normalizes to lowercase |
| *(not in SECRETS.h but required)* | Spot document fields `sensor_mac` / `camera_mac` | Set them in Firestore to the MACs each board prints on its serial monitor at boot (uppercase `AA:BB:...` format is safest — lookup tries exact/upper/lower) |

### Must match the physical hardware pair

| Constant | Set to | Gotchas |
|---|---|---|
| `PARKME_CAMERA_ESPNOW_PEER_MAC` | The **camera's STA MAC** (printed at camera boot) | Wrong/empty MAC still works via broadcast fallback, but direct send is more reliable. Both boards must be on the same WiFi **channel** (same AP) for ESP-NOW to pair with WiFi active |

### API paths (leave as-is — they match `main.py`)

```c
PARKME_API_UPDATE_SPOT_PATH   = "/api/v1/sensors/heartbeat"
PARKME_API_GATE_ENTRY_PATH    = "/api/v1/sensors/park"
PARKME_API_DISPLAY_POLL_PATH  = "/api/v1/displays/poll"
PARKME_API_DISPLAY_RESULT_PATH= "/api/v1/displays/result"
```

### Tuning values (defaults are fine; touch only if needed)

- Sensor: trigger/echo/battery/calibrate pins, `PARKME_SENSOR_OCCUPIED_THRESHOLD_CM` (20), sample interval (500 ms), heartbeat interval (20 s), HTTP timeout (2.5 s)
- Camera: flash LED pin (4), relay pin (−1 = gate relay disabled), HTTP timeout (7 s)
- Display: I2C pins (SDA 21 / SCL 22), address `0x3C`, `PARKME_DISPLAY_COLUMN_OFFSET` (0–2 if text is shifted)
- `PARKME_GATE_MAX_CAPTURE_RETRIES` exists but is **unused** — upload attempts are hardcoded to 3 in `captureAndUpload()`

### After editing SECRETS.h

Reflash **both** boards (each compiles SECRETS.h in), watch serial at 115200 for: WiFi IP + MAC, `Backend: https://<host>:443`, `[SSE] Stream connected.` (sensor), and `Gate spot: C1` (camera). Then update the Firestore spot doc MACs if the boards changed.

---

## 6. Deployment Order (summary)

1. Enable APIs, billing, IAM role (§1)
2. ~~Apply the code fixes~~ — already done (§2); nothing to do
3. `gcloud run deploy` with the flags in §3 → note the service URL
4. Seed Firestore + Auth users if not done
5. Deploy frontend to Firebase Hosting; point `app.js` at the service URL; lock down CORS
6. Fill `SECRETS.h` with the service host (§5); flash both boards
7. Set `sensor_mac`/`camera_mac` on the spot documents from the boards' serial output
8. Run the verification checklist (§3) end-to-end with a real car/object
