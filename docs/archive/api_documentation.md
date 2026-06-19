# ParkMe API Documentation

This file is a lightweight route summary for the current backend.

For the main migration and setup notes, prefer the files in `Documentation/`.

> The frontend is served directly by FastAPI through `StaticFiles`, so the same server can host both the API and the local dashboard UI.

## Current Auth Model

- Web users sign in with Firebase Authentication.
- Protected backend routes expect a Firebase ID token in the `Authorization` header.
- The backend verifies the token and then loads the matching Firestore user profile.

## Current Main Routes

### `POST /api/v1/sensors/heartbeat`

Purpose:

- update a parking spot's live hardware status

Payload:

```json
{
  "mac_address": "AA:BB:CC:DD:EE:01",
  "is_occupied": true,
  "battery_level": 92.0
}
```

Notes:

- the backend resolves the spot by `mac_address`
- the route creates or closes active parking logs as needed
- this is also where ghost `UNIDENTIFIED` occupancy can be created when a sensor reports occupied before a valid camera event arrives

### `POST /api/v1/sensors/park`

Purpose:

- receive an image from the ESP32-CAM and evaluate the parking event

Request type:

- `multipart/form-data`

Fields:

- `spot_id` as text
- `file` as the uploaded image

Notes:

- OCR is performed through Google Cloud Vision
- the backend looks up the spot, vehicle, and user in Firestore
- the response returns `action` and `message` fields used by the gate LCD and relay logic
- duplicate reads within a short window are dropped with a `RETRY` action

### `GET /api/v1/users/me`

Purpose:

- return the authenticated dashboard user's profile

Auth:

- `Authorization: Bearer <firebase-id-token>`

### `GET /api/v1/spots`

Purpose:

- return the visible parking spots for the current user

Auth:

- `Authorization: Bearer <firebase-id-token>`

Notes:

- admins see more operational detail
- standard users receive role-filtered spot data

### `GET /api/v1/logs`

Purpose:

- return recent violation or unidentified log events for admins

Auth:

- `Authorization: Bearer <firebase-id-token>`

### `GET /api/v1/stream`

Purpose:

- provide live SSE updates to the dashboard

Auth:

- `token` query parameter containing a Firebase ID token

Notes:

- `spot_update` events are filtered by role
- `log_event` messages are only sent to admins

### `PUT /api/v1/sensors/resolve`

Purpose:

- allow an admin to resolve an `UNIDENTIFIED` parking event

Auth:

- `Authorization: Bearer <firebase-id-token>`

Payload:

```json
{
  "spot_id": "A1"
}
```

### `POST /api/v1/telemetry/bulk`

Purpose:

- accept cached sensor events uploaded in bulk

Payload:

```json
{
  "mac_address": "AA:BB:CC:DD:EE:01",
  "data": [
    { "t": 1718520000, "v": true }
  ]
}
```

## Removed Route

The old backend login route is no longer part of the current architecture:

- removed: `POST /api/v1/auth/login`

Login is now handled by Firebase Authentication in the frontend.
