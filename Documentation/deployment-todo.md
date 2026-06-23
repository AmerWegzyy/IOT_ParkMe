# Deployment To-Do List & Guide

This document outlines the final steps required to take the ParkMe system from a local development environment to a fully deployed, internet-accessible production environment.

## 1. Deploying the Backend (Google Cloud Run)
Currently, the FastAPI backend runs locally on your machine (`http://localhost:8000`). To deploy it so the ESP32 microcontrollers and the web dashboard can access it from anywhere in the world, we recommend Google Cloud Run.

### Step-by-Step Guide:
1. Ensure you have a `Dockerfile` in the `Backend/` directory (we can generate one if you don't have it yet).
2. Install the [Google Cloud CLI (gcloud)](https://cloud.google.com/sdk/docs/install) and authenticate your account by running:
   ```bash
   gcloud auth login
   gcloud config set project [YOUR_GOOGLE_CLOUD_PROJECT_ID]
   ```
3. Open a terminal in the `Backend/` directory and run the deployment command:
   ```bash
   gcloud run deploy parkme-backend --source . --region us-central1 --allow-unauthenticated
   ```
4. Once deployed, the console will output a secure Service URL (e.g., `https://parkme-backend-xxxxx-uc.a.run.app`). Save this URL.

### The Refactor Prompt:
When you have successfully deployed the backend and obtained the Cloud Run URL, copy and paste this exact prompt to me so I can update the codebase:

> "I have deployed the backend to Cloud Run. The new backend URL is `[YOUR_CLOUD_RUN_URL]`. Please refactor the codebase to point to this new URL instead of `localhost`. Make sure to update the Vanilla JS Frontend API calls, the ESP32 `SECRETS.h` host/scheme, and verify that the backend's CORS is properly configured."

---

## 2. Deploying the Frontend (Firebase Hosting)
Currently, the frontend is served locally. Because we are already heavily utilizing Firebase Auth and Firestore, Firebase Hosting is the perfect, free solution to host the Vanilla HTML/JS frontend.

### Step-by-Step Guide:
1. Install the [Firebase CLI](https://firebase.google.com/docs/cli) globally via npm:
   ```bash
   npm install -g firebase-tools
   ```
2. Authenticate the Firebase CLI by running:
   ```bash
   firebase login
   ```
3. Open a terminal in the root of the project (where your `firebase.json` is located).
4. If you haven't initialized hosting yet, run `firebase init hosting`, select your existing Firebase project, and type `Frontend` when asked for the public directory. Answer `No` to the single-page app question.
5. Deploy the frontend to the world by running:
   ```bash
   firebase deploy --only hosting
   ```
6. Firebase will output a live Hosting URL (e.g., `https://your-project-id.web.app`).

### The Refactor Prompt:
When you deploy the frontend, you'll want to lock down the backend so that only your deployed frontend is allowed to talk to it. Copy and paste this exact prompt to me when you are ready:

> "I am deploying the frontend to Firebase Hosting. My Firebase Hosting URL is `[YOUR_FIREBASE_HOSTING_URL]`. Please update the CORS policy in the backend `main.py` to strictly allow this specific origin instead of `*` for production security."
