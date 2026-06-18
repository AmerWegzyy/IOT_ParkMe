# ParkMe To-Do List & Deployment Roadmap

The core application logic, database, and hardware integrations are currently stable and functional. The next phase focuses entirely on **Deployment, Security, and Quality Assurance**.

---

## Outstanding Tasks

- [ ] **Create Firestore Composite Indexes** (See guide below)
- [ ] **Write Automated Tests** 
  * Create `pytest` suites to validate backend endpoints, specifically testing the self-healing and bouncing driver edge cases.
- [ ] **Deploy Frontend to Firebase Hosting** (See guide below)
- [ ] **Deploy Backend to Google Cloud Platform** (See guide below)

---

## Deployment Playbook

Follow these exact steps to take the project from `localhost` to production.

### Step 0: Creating Firestore Composite Indexes (Database Prep)
The backend's heartbeat logic requires a complex query to resolve ghost logs and calculate parking durations. Firestore requires explicit composite indexes for this, otherwise the backend will crash with a `500 FailedPrecondition` error.

There are two ways to create this index:

**Method 1: The Automatic Link (Recommended)**
1. Run the backend locally (`fastapi dev main.py`).
2. Trigger a heartbeat event from the ultrasonic sensor (or via Postman/curl).
3. The backend will crash and print a long `FailedPrecondition` error in the terminal containing a direct Google Cloud link.
4. `Ctrl+Click` that link. It will open your browser directly to the Firebase Console with the exact index pre-configured.
5. Click **Create Index** and wait 3-5 minutes for it to build.

**Method 2: Manual Creation via Firebase Console**
1. Go to the [Firebase Console](https://console.firebase.google.com).
2. Select your project (`parkme-technion-f280b`).
3. In the left sidebar, click **Firestore Database**, then click the **Indexes** tab.
4. Click the **Add Index** button.
5. Set the Collection ID to `parking_logs`.
6. Add the following fields exactly in this order:
   - `spot_id` : **Ascending**
   - `exit_time` : **Ascending**
   - `entry_time` : **Descending**
7. Set Query scopes to **Collection**.
8. Click **Create Index** and wait 3-5 minutes for it to build.

### Step 1: Enabling Google Cloud APIs (Required for OCR)
The camera OCR relies entirely on the Google Cloud Vision API. Whether running locally or in production, you must manually enable this API in your project, or the backend will crash with a `403 Forbidden` error.

1. **Navigate to the Google Cloud Console:** Go to [console.cloud.google.com](https://console.cloud.google.com).
2. **Select the Project:** Ensure your active project is `parkme-technion-f280b`.
3. **Enable the API:** Search for "Cloud Vision API" in the top search bar, or navigate directly to the API Library and click the blue **Enable** button.
4. **Billing Verification:** Ensure your project has an active Billing Account attached. Cloud Vision offers a generous free tier (1,000 units/month), but Google requires a billing account to prevent abuse.
5. **Propagation Time:** Wait 2-5 minutes after clicking Enable for the API activation to propagate through Google's servers before testing the camera.

### Step 2: Deploying the Frontend (Firebase Hosting)
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
5. **Update API URL:** Once the backend is deployed (Step 3), open `Frontend/app.js` and update the `API_BASE` variable to point to your new Cloud Run URL instead of `localhost:8000`.

### Step 3: Deploying the Backend (Google Cloud Run)
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
   In the Google Cloud Console, navigate to Cloud Run -> `parkme-api` -> Edit & Deploy New Revision -> Variables & Secrets. Add the following:
   * `GOOGLE_APPLICATION_CREDENTIALS` (Bind this to your Firebase Service Account JSON using Google Secret Manager for maximum security).
5. **Hardware Update:** Finally, update the `PARKME_SERVER_HOST` in your ESP32 `SECRETS.h` to point to the new Cloud Run URL (without the `https://`).
