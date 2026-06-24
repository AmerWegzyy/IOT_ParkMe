# Recent Development Summary

This document outlines the major cleanup, feature additions, and bug fixes made to the ParkMe system after migrating entirely to a Firestore-based architecture.

## 1. Cleanup of Outdated Architecture
- **Removed Local Storage**: Completely deleted the `Backend/captures/` directory and stripped out all code that saved camera captures to the local disk.
- **Removed SQLite**: Deleted `Backend/schema.sql` and all references to local relational databases, solidifying Firestore as the single source of truth.
- **Removed "Resolve" Flow**: Stripped out the ambiguous "Resolve" endpoint and UI. The system now strictly relies on clear `Accept` or `Reject` actions for manual review.
- **Removed Dead Code**: Cleaned up dangling constants (e.g., `CAMERA_COMMAND_STALE_SECONDS` which caused a `NameError` on boot) and deprecated camera polling logic.

## 2. Violation Evidence Feature (Base64 Integration)
- **Base64 Encoding**: Instead of relying on Firebase Storage or a local filesystem, the backend now encodes ESP32-CAM JPEG captures as Base64 strings.
- **Standard Violations**: If a license plate is recognized by Google Vision but the user is unregistered, the base64 image is immediately saved directly into the `parking_logs` document as `capture_base64`.
- **Manual Review Rejections**: If the camera fails to read a plate (`UNIDENTIFIED`), the image is stored in `spot_captures`. If the admin manually clicks "Reject", the backend pulls the image from `spot_captures` and permanently attaches it to the resulting violation log.
- **Realtime UI "Show Picture"**: The Vanilla JS frontend (`app.js`) listens for SSE `log_event` broadcasts. When a violation occurs, a "Show Picture" button is dynamically appended to the Security Log without a page refresh. Clicking it hits the new `GET /api/v1/logs/{log_id}/capture` endpoint to render the decoded evidence.

## 3. Realtime UI & Log Bug Fixes
- **Bouncy Driver Reversion**: Handled the edge case where a bouncy driver triggers a violation but vacates the spot within the 90-second grace period. The backend broadcasts a `log_aborted` SSE event, and the frontend instantly rewrites the log text to "Driver aborted parking" and removes the "Show Picture" button.
- **Event Type Consistency**: Fixed a bug where unauthorized (but clearly read) plates were being broadcast as `"unidentified"` over SSE, which prevented the "Show Picture" button from mounting on initial load.
- **Admin Action Logs**: Changed the log behavior for manual rejections. Instead of creating a log that says "Admin rejected vehicle", the system now correctly logs it as "Violation at Spot X (Unidentified Plate)" so it behaves exactly like a normal violation and retains the evidence button.

## 4. Documentation Overhaul
- **Ground Truth Restoration**: Restored `Documentation/PROJECT_STATE_CURRENT.md` as the definitive guide to the system.
- **Edge Cases & Timings**: Documented the 10-second camera grace period, the 90-second bouncy driver window, network loss telemetry caching, and manual UI timeouts.
- **Database Schema**: Documented the active Firestore collections (`parking_spots`, `users`, `vehicles`, `parking_logs`, `spot_captures`).
- **Hardware Team Guide**: Authored `hardware-code-upload-guide.md` to clearly instruct teammates on how to flash the `ParkMeSensorNode` (standard ESP32) and `ParkMeCameraNode` (ESP32-CAM), including IDE configurations and the shared `SECRETS.h`.

## 5. SSE & Dual-Core Architecture Upgrade
- **Zero-Latency Displays**: Replaced the Firestore-based polling queue for the LCD displays with a direct Server-Sent Events (SSE) stream (`/api/v1/displays/stream`), pushing display updates instantly from the backend to the hardware without database latency.
- **FreeRTOS Dual-Core Split**: Upgraded the `ParkMeSensorNode` firmware to run its network operations (WiFi, SSE stream, Telemetry) on Core 0 as a background task, ensuring the main loop on Core 1 remains 100% responsive for ultrasonic sampling and OLED rendering.
- **In-Memory Fallback**: Replaced the Firestore `display_commands` collection with an in-memory dictionary. If the SSE stream disconnects, the ESP32 gracefully falls back to polling the in-memory store until it reconnects with exponential backoff.
