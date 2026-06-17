# ParkMe Master Guide: Architecture, Behaviors, and Edge Cases

This document serves as the **Master Guide** for the ParkMe project. It is designed to give the development team a comprehensive, top-to-bottom understanding of how the system operates, how the microservices communicate, how edge cases are gracefully handled, and the roadmap for deployment.

---

## 1. System Architecture: "Who Sends Packets to Who"

The ParkMe ecosystem relies on decoupled microservices communicating over HTTP, authenticated APIs, and real-time Server-Sent Events (SSE). 

### The Core Pillars
1. **Edge Layer:** The ESP32 microcontrollers deployed at the parking spot (Sensor Node) and at the entrance gate (Camera Node).
2. **Backend Brain:** A FastAPI server (soon to be hosted on Google Cloud Run) responsible for orchestrating logic, talking to AI models, and real-time broadcasting.
3. **AI Layer:** Google Cloud Vision API, used for high-accuracy License Plate Recognition (OCR).
4. **Data Layer:** Firebase Firestore (NoSQL database) and Firebase Authentication.
5. **Presentation Layer:** The Web Dashboard (HTML/JS) running on the driver's phone or administrator's computer.

### The Standard "Vehicle Parks" Workflow
When a registered driver approaches the parking gate, the following sequence occurs:

1. **Gate Trigger (Hardware $\rightarrow$ Backend):**
   * The **Camera Node**'s ultrasonic sensor detects a vehicle within 50 cm.
   * The camera flashes its LED for 80ms, snaps a JPEG, and sends a `multipart/form-data` request via raw TCP HTTP/1.1 to the Backend at `POST /api/v1/sensors/park`.
2. **OCR Processing (Backend $\leftrightarrow$ Cloud Vision):**
   * The Backend receives the JPEG and immediately forwards it to the **Google Cloud Vision API**.
   * Cloud Vision returns the extracted text, which the backend parses to isolate the license plate.
3. **Database Validation (Backend $\leftrightarrow$ Firestore):**
   * The Backend queries the `vehicles` collection to find the car owner's ID, then queries the `users` collection to check their role (e.g., `student`, `lecturer`).
   * It cross-references the user's role against the spot's `category`. If authorized, `is_violation = False`. If unauthorized or unregistered, `is_violation = True`.
   * A new record is created in the `parking_logs` collection.
4. **Gate Response (Backend $\rightarrow$ Hardware):**
   * The Backend responds to the Camera Node with a JSON payload: `{"action": "WELCOME", "message": "Welcome, John!"}`.
   * The Camera Node parses this, displays the message on the I2C LCD, and triggers a 3-second HIGH pulse on its relay pin to open the physical gate barrier.
5. **Real-Time UI Update (Backend $\rightarrow$ Frontend):**
   * The Backend immediately fires a Server-Sent Event (SSE) named `spot_update` down a persistent connection to the Web Dashboard.
   * The UI updates instantly, turning the spot red (Occupied) and displaying the driver's license plate, without the user needing to refresh the page.

### The "Continuous Heartbeat" Workflow
To ensure system health and track departures:
1. **Instant State Changes:** If a car leaves, the **Sensor Node** instantly fires a payload to `POST /api/v1/sensors/heartbeat` with `is_occupied: False`.
2. **Periodic Check-ins:** If the state hasn't changed, the Sensor Node sends a heartbeat every **6 minutes** to the same endpoint, reporting its battery level to prove it hasn't died.

---

## 2. Advanced Edge Cases & System Resiliency

The physical world is chaotic. Here is exactly how the current backend and frontend implementations handle anomalies.

### A. The "Bouncing Driver" (Aborted Sessions)
* **The Scenario:** A driver enters a spot, but realizes it's the wrong category (or they forgot something) and leaves 30 seconds later.
* **The Handling:** The Sensor Node instantly reports `OCCUPIED` (T=0) and then `FREE` (T=30s). The backend calculates the duration. Because 30s < 60s, the backend intercepts the departure and marks the log as `"ABORTED"` with `is_violation = False`. The driver is safely ignored and not penalized.

### B. Camera OCR Race Conditions & Ghost Cars (Self-Healing)
* **The Scenario:** The Sensor Node's tiny JSON heartbeat (`OCCUPIED`) travels over Wi-Fi faster than the Camera Node's heavy JPEG upload. The backend realizes a car is physically in the spot, but it has no idea who it is yet.
* **The Handling:** 
   1. The backend immediately creates a **Ghost Log** with `license_plate: "UNIDENTIFIED"` and `is_violation: True`.
   2. 1-2 seconds later, the delayed camera payload arrives and the OCR finishes.
   3. **Self-Healing Logic:** Before creating a new log, the backend checks for an active `UNIDENTIFIED` log for that spot. It finds it, and **overwrites it in-place** with the real driver's data. The system heals itself without any human intervention.

### C. Complete Camera Failure (The 45-Second Freeze)
* **The Scenario:** A car parks, but the Camera Node's Wi-Fi drops completely. The Sensor Node creates the `UNIDENTIFIED` Ghost Log, but the camera's payload *never* arrives to heal it.
* **The Handling:** 
   1. The Camera Node has a built-in resiliency loop: it will retry its network request up to **3 times** (each with a 10s timeout). 
   2. To prevent an admin from manually resolving the spot while the camera is still retrying, the Frontend UI enforces a **45-second freeze** on the "Acknowledge & Resolve" button. The UI shows a live countdown: *"Camera Retrying... (X s)"*.
   3. Once 45 seconds elapse (guaranteeing the camera has officially given up), the button unlocks. The admin can click it, triggering `PUT /api/v1/sensors/resolve`, which safely clears the violation and marks the plate as `"RESOLVED"`.

### D. Double Triggers (LPR Deduplication)
* **The Scenario:** The camera node accidentally captures and sends the same vehicle's license plate multiple times in rapid succession. This typically happens for two reasons:
   1. **Physical Fluctuation:** The driver creeps forward slowly, causing the ultrasonic sensor's distance reading to bounce back and forth across the 50cm trigger threshold.
   2. **Network Stutter:** The camera sends the image successfully, but the Wi-Fi drops before the backend's `200 OK` acknowledgment arrives. The camera assumes failure and aggressively retries sending the same image.
* **The Handling:** 
   1. To prevent spamming the database with duplicate parking logs and triggering multiple SSE UI broadcasts, the backend maintains an in-memory dictionary called `LPR_DEDUP_CACHE`.
   2. When a plate is parsed by the Cloud Vision API, the backend checks this cache. If the exact same license plate was processed within the last **5 seconds**, the backend intercepts the request and aborts the database write.
   3. The backend responds to the camera with:
      `{"status": "dropped", "reason": "duplicate_within_5s", "action": "RETRY", "message": "Processing..."}`
   4. The hardware receives the `"RETRY"` action, which tells the camera to pause and try again, effectively pacing the hardware and preventing further spam while the gate logic settles.

### E. Sensor Node Network Loss (NVS Caching)
* **The Scenario:** The Sensor Node's Wi-Fi drops exactly as a car leaves.
* **The Handling:** The Sensor Node writes the failed telemetry (Spot ID, Battery %, `FREE` state) into its non-volatile flash memory (NVS). Once the Wi-Fi connection is re-established, the background loop automatically flushes the pending telemetry to the backend, ensuring no events are permanently lost.

---

## 3. Admin Security Logs & Message Types

The web dashboard provides administrators with a real-time historical ledger of the 50 most recent events across all parking spots, fetched via `GET /api/v1/logs`. This endpoint queries the `parking_logs` Firestore collection natively ordered by `entry_time DESCENDING`.

A log is added to the database anytime the system detects physical occupancy (via the Sensor Node) or processes a license plate (via the Camera Node). Based on the backend's evaluation of the event, the log is classified into one of four UI messages:

1. 🔴 **`Unauthorized access at Spot {X} (Plate: {Y})`**
   * **Trigger:** The camera successfully read the plate, but the user's role does not match the spot's category (or the vehicle is unregistered).
   * **UI Styling:** Red text (`violation` CSS class).

2. ⚠️ **`Camera failure detected at Spot {X}.`**
   * **Trigger:** The Sensor Node detects occupancy and creates a ghost log, but the Camera Node completely fails to send a payload, leaving the plate as `UNIDENTIFIED`.
   * **UI Styling:** Yellow text (`unidentified` CSS class).

3. ⚪ **`Admin resolved anomaly at Spot {X}.`**
   * **Trigger:** The administrator manually clicked the "Acknowledge & Resolve" button on an active `UNIDENTIFIED` anomaly. The backend sets `is_violation: False` and updates the plate to `"RESOLVED"`.
   * **UI Styling:** Default info text.

4. ⚪ **`Driver aborted parking at Spot {X}.`**
   * **Trigger:** The "Bouncing Driver" scenario. A driver occupied the spot but left within 60 seconds. The backend sets `is_violation: False` and updates the plate to `"ABORTED"`.
   * **UI Styling:** Default info text.


---

## 4. Current Project To-Do List

The core application logic, database, and hardware integrations are currently stable and functional. The next phase focuses entirely on **Deployment, Security, and Quality Assurance**.

- [ ] **Create Firestore Composite Indexes:** The database requires composite indexes for complex heartbeat and bulk data queries to prevent `500 Internal Server Error (FailedPrecondition)` crashes.
  * **Required Index:** Collection Group `parking_logs`, indexed on `spot_id` (Ascending) + `exit_time` (Ascending) + `entry_time` (Descending).
  * **How to fix:** Either click the auto-generated link in the backend server's error log, or manually navigate to the Firebase Console -> Firestore -> Indexes -> Composite, and create the index.
- [ ] **Write Automated Tests:** Create `pytest` suites to validate backend endpoints, specifically testing the self-healing and bouncing driver edge cases.
- [ ] **Enforce HMAC Security:** The backend currently has `verify_hmac_signature` logic, but it is marked as *optional* because the ESP32 firmware does not currently hash its requests. The firmware must be updated to compute an HMAC-SHA256 hash using `PARKME_HARDWARE_HMAC_SECRET` and send `X-Signature` headers.
- [ ] **Deploy Frontend to Firebase Hosting** (See guide below)
- [ ] **Deploy Backend to Google Cloud Platform** (See guide below)

---

## 4. Deployment Playbook

Follow these exact steps to take the project from `localhost` to production.

### Step 0: Enabling Google Cloud APIs (Required for OCR)
The camera OCR relies entirely on the Google Cloud Vision API. Whether running locally or in production, you must manually enable this API in your project, or the backend will crash with a `403 Forbidden` error.

1. **Navigate to the Google Cloud Console:** Go to [console.cloud.google.com](https://console.cloud.google.com).
2. **Select the Project:** Ensure your active project is `parkme-technion-f280b`.
3. **Enable the API:** Search for "Cloud Vision API" in the top search bar, or navigate directly to the API Library and click the blue **Enable** button.
4. **Billing Verification:** Ensure your project has an active Billing Account attached. Cloud Vision offers a generous free tier (1,000 units/month), but Google requires a billing account to prevent abuse.
5. **Propagation Time:** Wait 2-5 minutes after clicking Enable for the API activation to propagate through Google's servers before testing the camera.

### Step 1: Deploying the Frontend (Firebase Hosting)
Since the frontend is pure HTML/JS/CSS, Firebase Hosting is the fastest, globally-distributed CDN for it.

1. **Install Firebase CLI:**
   ```bash
   npm install -g firebase-tools
   ```
2. **Login and Initialize:**
   Navigate to your project root (or the `Frontend` folder) and run:
   ```bash
   firebase login
   firebase init hosting
   ```
3. **Configuration:**
   * Select your existing Firebase project (`parkme-technion-f280b`).
   * When asked "What do you want to use as your public directory?", type `Frontend` (or the folder containing `index.html`).
   * Configure as a single-page app? `No`.
   * Set up automatic builds with GitHub? `No` (for now).
4. **Deploy:**
   ```bash
   firebase deploy --only hosting
   ```
   *Firebase will give you a live HTTPS URL (e.g., `https://parkme-technion-f280b.web.app`).*
5. **Update API URL:** Once the backend is deployed (Step 2), open `Frontend/app.js` and update the `API_BASE` variable to point to your new Cloud Run URL instead of `localhost:8000`.

### Step 2: Deploying the Backend (Google Cloud Run)
Cloud Run is perfect for FastAPI: it auto-scales to zero (saving money) and scales up instantly when a car parks.

1. **Prepare the Dockerfile:**
   Create a `Dockerfile` inside the `Backend` directory:
   ```dockerfile
   FROM python:3.12-slim
   WORKDIR /app
   COPY requirements.txt .
   RUN pip install --no-cache-dir -r requirements.txt
   COPY . .
   EXPOSE 8080
   CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
   ```
2. **Authenticate with Google Cloud:**
   ```bash
   gcloud auth login
   gcloud config set project parkme-technion-f280b
   ```
3. **Build and Deploy:**
   Run the following command from inside the `Backend` directory. Cloud Build will package your app and deploy it.
   ```bash
   gcloud run deploy parkme-api \
     --source . \
     --region europe-west1 \
     --allow-unauthenticated \
     --port 8080
   ```
4. **Set Environment Variables:**
   In the Google Cloud Console, navigate to Cloud Run $\rightarrow$ `parkme-api` $\rightarrow$ Edit & Deploy New Revision $\rightarrow$ Variables & Secrets. Add the following:
   * `PARKME_HARDWARE_HMAC_SECRET`
   * `GOOGLE_APPLICATION_CREDENTIALS` (Bind this to your Firebase Service Account JSON using Google Secret Manager for maximum security).
5. **Hardware Update:** Finally, update the `PARKME_SERVER_HOST` in your ESP32 `SECRETS.h` to point to the new Cloud Run URL (without the `https://`).
