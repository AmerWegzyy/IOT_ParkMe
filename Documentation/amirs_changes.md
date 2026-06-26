# Amir's Changes Log

This file documents recent fixes, feature additions, and system modifications. Future changes should be appended to this document to maintain a clean history.

## June 26, 2026 - Camera Retries and Buffer Fixes

### 1. ESP32-CAM (`ParkMeCameraNode.ino`)
- **Fixed Stale "Old Photo" Issue:** The ESP32-CAM hardware utilizes a PSRAM DMA FIFO buffer that holds up to 2 frames (`config.fb_count = 2`). Previously, the node only performed one "dummy grab" before capturing the photo, which resulted in the oldest stale frame being uploaded. Added a **second dummy grab** to completely flush the FIFO buffer, guaranteeing a 100% fresh photo on every capture.
- **Implemented Instant HTTP Retries:** Removed the buggy PSRAM caching system. Instead, if `captureAndUpload` fails due to a network connection error or a backend timeout, the camera will immediately retry sending the *exact same photo frame* up to 3 times. This satisfies the requirement of trying to resend the photo without capturing a new one, while preventing memory leaks or indefinite stalling.
- **Implemented Instant Upload Abort on Spot Free:** Added a thread-safe helper `checkIfSpotBecameFree()` that continuously checks the incoming ESP-NOW message buffer during the HTTP retry loop. If the sensor broadcasts a `STATE_FREE` message (indicating the car left) while the camera is still retrying or waiting for the backend, the camera will instantly abort the upload sequence and drop the photo, freeing up the hardware immediately.

### 2. Backend (`main.py`)
- **Fixed UI Stuck on "Waiting for camera image":** Replaced Python's default `json.dumps()` in the Server-Sent Events (SSE) `broadcast_event` function with FastAPI's `jsonable_encoder`. Previously, broadcasting a payload containing `datetime` objects caused a silent crash, preventing the frontend from receiving the event that the spot was free. `jsonable_encoder` safely converts `datetime` objects to ISO format strings.
- **Restored Async Broadcasts for Sync Endpoints:** Re-added the `main_loop` capture during startup and the `run_async_in_main` helper function, allowing synchronous endpoints to safely push SSE events to the main asyncio loop.
