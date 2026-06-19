# ParkMe Project Summary

This is a current summary of the repository after the Google Cloud and Firebase migration.

For the detailed setup and migration docs, use the files in `Documentation/`.

## Core Architecture

ParkMe is an event-driven smart parking system made of:

- ESP32 sensor nodes
- ESP32-CAM image capture nodes
- a FastAPI backend
- Firebase Firestore
- Firebase Authentication
- Google Cloud Vision API
- a static web dashboard

## Runtime Flow

### Hardware

- sensor nodes send occupancy and battery heartbeats
- camera nodes upload parking images
- the backend updates Firestore and broadcasts live SSE events

### Backend

- runs on Google Cloud Run
- uses Firestore for application data
- uses Cloud Vision for OCR
- verifies Firebase ID tokens for dashboard users

### Frontend

- authenticates with Firebase Auth
- fetches profile, spots, and logs from the backend
- receives live updates through SSE
- can be hosted on Firebase Hosting

## Main Data Model

Firestore currently stores:

- `users`
- `vehicles`
- `parking_spots`
- `parking_logs`

Firebase Authentication stores credentials separately from those Firestore collections.

## Current Development Notes

- SQL files and SQL queries were removed from the main backend path.
- The old custom backend login endpoint was removed.
- Local development needs Google credentials and a Firebase project.
- The frontend still needs the real Firebase web config and the deployed Cloud Run URL.
- The ESP32 firmware still needs a local `SECRETS.h` file and final backend host values.
