# ParkMe — Software Stack: Names & Versions

Exact versions the project was built and verified with (course requirement:
library names + versions, SDK version).

## Firmware (ESP32)

| Item | Version / value |
|---|---|
| Arduino ESP32 board package (Espressif `esp32`) | **2.0.17** <!-- TODO: confirm on the flashing PC (Arduino IDE → Boards Manager → esp32) --> |
| Sensor node board profile | ESP32 Dev Module |
| Camera node board profile | AI Thinker ESP32-CAM |

All firmware libraries are **bundled with the ESP32 core 2.0.17** — no external
Arduino libraries are installed:

| Library | Used for |
|---|---|
| `WiFi`, `WiFiClientSecure` | hotspot connection, HTTPS to Cloud Run |
| `HTTPClient` | REST calls (sensor node) |
| `Wire` | I2C (OLED display) |
| `Preferences` | NVS flash persistence (calibration, offline queue) |
| `esp_now` | sensor → camera trigger link |
| `esp_camera` | OV2640 capture (camera node) |

Custom in-repo firmware modules (no version — part of this repository):
`ParkMeCommon.h`, `ParkMeConfig.h`, `ParkMeLcd.h` (custom raw-I2C display
drivers — this is also why no Adafruit libraries are needed).

## Backend (deployed on Google Cloud Run, region `me-west1`)

Exact versions from the container image built and deployed on 2026-07-20
(Cloud Build log, revision `parkme-backend-00004-cmz`).

| Item | Version |
|---|---|
| Python | **3.11** (base image `python:3.11-slim`) |
| fastapi | 0.139.2 |
| starlette | 1.3.1 |
| uvicorn | 0.51.0 |
| pydantic | 2.13.4 (core 2.46.4) |
| firebase-admin | 7.5.0 |
| google-cloud-firestore | 2.28.0 |
| google-cloud-vision | 3.15.0 |
| google-cloud-storage | 3.13.0 |
| google-cloud-core | 2.6.0 |
| python-dotenv | 1.2.2 |
| python-multipart | 0.0.32 |
| cachetools | 7.1.4 |
| tzdata | 2026.3 |

`Backend/requirements.txt` intentionally uses minimum-version ranges (`>=`) for
installation flexibility; the table above records the exact versions actually
built into the deployed container (from the Cloud Build install log).

## Frontend (Firebase Hosting)

| Item | Version |
|---|---|
| Stack | Vanilla HTML / CSS / JavaScript (no build step, no framework) |
| Firebase JS SDK (`firebase-app-compat`, `firebase-auth-compat`, CDN) | **10.8.0** |
| Google Fonts | Inter (CDN) |

## Cloud services

| Service | Role |
|---|---|
| Google Cloud Run | FastAPI backend container (built with Cloud Build, `Backend/cloudbuild.yaml` + `Dockerfile`) |
| Google Cloud Firestore | application database (spots, users, vehicles, logs, captures) |
| Firebase Authentication | dashboard login (email/password) |
| Firebase Hosting | static dashboard hosting |
| Google Cloud Vision API | license-plate OCR (`text_detection` + `document_text_detection`) |
