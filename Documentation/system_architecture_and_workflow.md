# ParkMe — System Architecture & Workflow

This document provides a high-level overview of how the different components of the ParkMe system communicate and work together to provide a seamless smart parking experience.

---

## 1. System Components

The ParkMe ecosystem consists of four main pillars:

1.  **Hardware (ESP32 Sensors):** The physical IoT edge devices deployed at each parking spot. They detect physical presence and capture images of license plates.
2.  **Backend (FastAPI on Google Cloud Run):** The central brain of the system. It handles business logic, security, image processing (OCR), and real-time event broadcasting.
3.  **Database (Firebase Firestore):** A NoSQL cloud database that stores all persistent data, including users, vehicles, parking spots state, and historical parking logs.
4.  **Frontend (Web App):** The user interface where drivers and administrators can view real-time parking availability and logs.

---

## 2. Architecture Diagram

```mermaid
graph TD
    subgraph Edge Layer
        ESP[ESP32 Node<br/>Camera + Proximity]
    end

    subgraph Cloud Layer (Google Cloud Platform)
        API[FastAPI Backend<br/>Google Cloud Run]
        DB[(Firebase Firestore<br/>NoSQL Database)]
    end

    subgraph Presentation Layer
        WEB[Web Dashboard<br/>HTML/CSS/JS]
    end

    %% Communication paths
    ESP -- 1. Heartbeats & Images<br/>(HMAC Secured) --> API
    API -- 2. Read/Write Data --> DB
    WEB -- 3. API Requests (JWT Auth) --> API
    API -- 4. SSE (Server-Sent Events) --> WEB
```

---

## 3. Core Workflows

### Scenario A: A Vehicle Parks (The "Park" Event)

1.  **Detection:** The ESP32 sensor detects a vehicle entering the parking spot using its proximity sensor.
2.  **Capture:** The ESP32 camera takes a snapshot of the vehicle's license plate.
3.  **Transmission:** The ESP32 securely sends the image to the backend via a `POST /api/v1/sensors/park` request, authenticated with an HMAC signature.
4.  **Processing (OCR):** The backend receives the image. It uses OpenCV to preprocess the image and Tesseract OCR to extract the license plate text.
5.  **Validation:** 
    *   The backend queries **Firestore** to find the vehicle associated with that license plate and its owner's role.
    *   It compares the owner's role with the parking spot's allowed category.
6.  **Database Update:** 
    *   A new entry is created in the `parking_logs` Firestore collection. If the user isn't allowed to park there (or is unregistered), it's flagged as a violation.
    *   The `parking_spots` Firestore document is updated to show `is_occupied: true`.
7.  **Real-Time Broadcast:** The backend sends a Server-Sent Event (SSE) to all connected Web App clients, immediately updating the UI to show the spot as taken (and triggering an alert if it's a violation).

### Scenario B: Continuous Monitoring (The "Heartbeat")

1.  **Periodic Check-in:** Every few seconds/minutes, the ESP32 sends a lightweight heartbeat to `POST /api/v1/sensors/heartbeat`. This includes the current physical occupancy and battery level.
2.  **Database Update:** The backend updates the corresponding spot in Firestore with the latest `last_seen` timestamp, battery level, and physical occupancy.
3.  **Anomaly Detection:** 
    *   **Ghost Car:** If the heartbeat says "occupied" but there is no active log (maybe the camera failed to capture the plate), the backend creates an "UNIDENTIFIED" log and flags a violation.
    *   **Bouncing Driver:** If a car leaves within 60 seconds of arriving, the backend intercepts the departure and marks the log as "ABORTED" instead of a completed parking session, canceling any potential violation.
4.  **Real-Time Broadcast:** Any changes in state are broadcasted via SSE to the web frontend.

### Scenario C: Web Frontend Usage

1.  **Login:** A user logs into the Web App. The frontend calls `POST /api/v1/auth/login`. The backend checks the credentials against Firestore and returns a JWT token.
2.  **Initial Load:** The frontend calls `GET /api/v1/spots` (with the JWT token). The backend fetches the current state of all spots from Firestore, filtering them based on the user's role (e.g., an admin sees everything, a student only sees student spots).
3.  **Live Updates:** The frontend opens a persistent connection to `GET /api/v1/stream`. It listens for SSE events. When a car parks or leaves, the backend pushes the update down this stream, and the frontend updates the map/list without needing to refresh the page.
4.  **Admin Resolution:** If an admin sees an "UNIDENTIFIED" car, they can manually inspect it and call `PUT /api/v1/sensors/resolve`. The backend updates the Firestore log to "RESOLVED" and clears the violation.

---

## 4. Security & Authentication

*   **Device-to-Cloud (ESP32 to Backend):** Uses **HMAC-SHA256 signatures**. The ESP32 and the Backend share a secret key (`ESP32_HMAC_SECRET`). Every request from the ESP32 is signed. The backend verifies the signature and checks a timestamp to prevent replay attacks. This ensures no one can spoof fake parking events.
*   **User-to-Cloud (Web App to Backend):** Uses **JWT (JSON Web Tokens)**. When a user logs in, they receive a signed token containing their role. They send this token in the `Authorization` header for subsequent requests. The backend decodes it to enforce role-based access control (RBAC).
*   **Cloud-to-Database (Backend to Firestore):** Uses **Google Application Default Credentials (ADC)** via the `serviceAccountKey.json`. This provides secure server-to-server authentication within Google's infrastructure.
