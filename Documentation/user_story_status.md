# ParkMe User Story Status

This file maps the current repository to the user stories from `ProjectDefinition`.

Status meanings:

- `Done`: implemented in the current codebase
- `Partial`: partly implemented, but still missing an important part
- `Open`: not complete yet

## 1. Availability

Status: `Done`

Why:

- The frontend shows live spot cards.
- The backend pushes updates over SSE.
- Occupancy comes from real sensor heartbeats.

## 2. LPR Access

Status: `Done`

Why:

- The camera uploads images to the backend.
- The backend uses Cloud Vision OCR.
- The backend compares the detected plate against Firestore users and vehicles.
- Role-based access is enforced by spot category.

## 3. Violation Alert

Status: `Done`

Why:

- Unauthorized access becomes a violation log.
- Admin users see live security log events.
- `UNIDENTIFIED` cases are surfaced immediately.

## 4. Accessible Parking

Status: `Partial`

Why:

- Special-needs spots exist as a separate category.
- Role filtering already limits visible spots to the relevant categories.
- The frontend now shows a recommended free visible spot.

What is still missing:

- A stronger dedicated "best accessible spot" guidance flow could still be added if you want route-quality recommendations instead of simple recommendation by first free visible spot.

## 5. Maintenance

Status: `Done`

Why:

- Sensor battery percentage is sent in heartbeats.
- Admin cards show battery and last ping time.

## 6. Display Access Status on Device Screen

Status: `Partial`

Why:

- The camera node prints status such as capture, retry, access granted, and access denied to the serial monitor.

What is still missing:

- A finished standalone display node for the `GME12864-77` screen that talks to the backend directly and shows the final user-facing message on real hardware.

## 7. Logs and Statistics

Status: `Done`

Why:

- Admin anomaly logs already existed.
- The backend now exposes usage statistics.
- The admin dashboard now shows summary statistics such as occupancy, total logs, violations, peak hour, and busiest spot.

## 8. Configuration

Status: `Done`

Why:

- Spot categories are configured from Firestore in `parking_spots`.
- The backend enforces permissions from that category mapping.

Note:

- Configuration is currently database-driven, not yet a dedicated admin form in the dashboard.

## 9. Edge-case and Offline Handling

Status: `Partial`

Why:

- Sensor-side NVS caching exists.
- Ghost logs, retries, self-healing, and aborted parking are handled.
- The dashboard now marks stale spots as `OFFLINE` and warns the admin when a node becomes stale.

What is still missing:

- There is still no out-of-band alert channel such as push notification, email, or SMS when no dashboard is open.

## 10. Graphical User Interface

Status: `Done`

Why:

- The project has a dedicated web app.
- Users authenticate with Firebase.
- The dashboard updates without page reloads.

## 11. Calibration / Setup Mode

Status: `Done`

Why:

- The spot sensor supports calibration by holding the button on GPIO 0.
- The baseline is stored and reused across restarts.

## Summary

Stories that are effectively done in the current repo:

- `1`, `2`, `3`, `5`, `7`, `8`, `10`, `11`

Stories that are partly done and still have a remaining gap:

- `4`, `6`, `9`

If you want the next highest-value work items, they are:

1. Build a real standalone display node for the `GME12864-77` screen.
2. Add a stronger accessible-spot recommendation strategy.
3. Add true out-of-band offline alerts when the admin dashboard is not open.
