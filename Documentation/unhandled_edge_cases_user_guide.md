# ParkMe User Guide for Edge Cases That Still Need Operator Attention

This guide is for the current local/server-centered ParkMe build.

Current local flow:

1. The spot sensor posts `/api/v1/sensors/heartbeat` when occupancy changes and on periodic keep-alives.
2. The backend updates Firestore and queues a capture command for the mapped camera.
3. The camera polls `/api/v1/cameras/poll`, captures only when commanded, uploads the image to `/api/v1/sensors/park`, and reports the result back to the backend.
4. The dashboard receives live `spot_update` and `log_event` messages over SSE.

## 1. Will polling cause delays?

Yes, but the delay is small and predictable in the current setup.

- The sensor update itself is push-based, so the spot occupancy reaches the backend immediately when the reading changes.
- The extra delay comes from the camera poll loop.
- `PARKME_GATE_COMMAND_POLL_INTERVAL_MS` is currently `2000`, so the backend command reaches the camera in `0-2` seconds.
- In practice, the average added wait is about `1` second.

This is acceptable for a parking and monitoring system, but it is not suitable for safety-critical gate control where sub-second guarantees are required.

## 2. Edge Cases That Are Handled Automatically

These already have automatic logic in the current build:

- Sensor Wi-Fi drop during a state change: the spot node caches one pending telemetry item in NVS and retries later.
- Temporary camera/OCR delay: the backend creates a ghost log and later self-heals it if the camera result arrives.
- Driver enters wrong spot then leaves quickly: the log becomes `ABORTED` instead of staying as a permanent violation.
- Duplicate OCR reads: the backend deduplicates repeated plate reads within a short time window.
- Missing heartbeats while the dashboard is open: the UI now marks the spot `OFFLINE` after two minutes with no heartbeat.

## 3. Edge Cases That Still Need Human Attention

### A. Sensor node goes silent while no admin dashboard is open

What you will see:

- No automatic popup is sent anywhere if nobody is watching the dashboard.
- Later, when the admin dashboard is opened, the spot can appear as `OFFLINE`.

What to do:

1. Check power to the ESP32 and the ultrasonic sensor.
2. Check that the hotspot or Wi-Fi is still on.
3. Confirm the backend host IP in `ESP32/SECRETS.h`.
4. Confirm the spot's `sensor_mac` in Firestore matches the real ESP32 MAC.

Current limitation:

- There is no out-of-band alert yet such as email, SMS, or Firebase Cloud Messaging.

### B. Camera captures an image but the plate is still unreadable

What you will see:

- The admin dashboard can show `UNIDENTIFIED`.
- Security logs can show `Camera failure detected at Spot <spot>`.
- After the retry cooldown, the admin can resolve the anomaly manually.

What to do:

1. Make sure the test target looks like a real plate with large dark digits on a bright background.
2. Move the plate closer and keep it centered.
3. Improve lighting and reduce glare.
4. Clean the camera lens.
5. Verify Cloud Vision API is enabled in Google Cloud.

Current limitation:

- If OCR keeps failing, a human must resolve the event manually.

### C. Firestore mapping is wrong

What you will see:

- Heartbeats return `202`, but the wrong spot updates.
- Camera uploads succeed, but the wrong spot gets the violation or occupancy change.
- A device appears to do "nothing" even though it is connected.

What to do:

1. Open Firestore `parking_spots`.
2. Check `sensor_mac` for the spot node.
3. Check `camera_mac` for the camera node.
4. Make sure each MAC belongs to the correct document.

Current limitation:

- Device identity is still controlled by database mapping, so a wrong MAC entry breaks routing.

### D. Missing Firestore composite indexes

What you will see:

- Backend `500` errors with `FailedPrecondition`.
- Heartbeats or log queries fail even though credentials are correct.

What to do:

1. Open `Documentation/to-do_list.md`.
2. Create the required `parking_logs` composite index.
3. Wait a few minutes for the index to finish building.

Current limitation:

- Firestore will not build these indexes automatically for you.

### E. Cloud Vision API disabled or billing not ready

What you will see:

- Camera upload reaches the backend, but OCR requests fail.
- Backend may return `403` errors or keep asking for retries.

What to do:

1. Open the Google Cloud Console.
2. Enable `Cloud Vision API`.
3. Confirm billing is attached to the project.
4. Wait `2-5` minutes for propagation.

Current limitation:

- OCR depends completely on this external Google API.

### F. Local authentication clock skew

What you will see:

- Backend logs like `Token used too early`.
- Frontend login succeeds, then protected endpoints return `401`.

What to do:

1. Sync the PC clock with Windows time settings.
2. Sign out and sign back in.
3. Restart the backend after the clock is fixed.

Current limitation:

- Firebase token validation is time-sensitive.

### G. Separate screen story is not fully closed yet

What you will see:

- The current local camera build prints access/debug status to the serial monitor.
- There is no finished standalone server-driven display node yet for the `GME12864-77` screen.

What to do:

1. Use the serial monitor for gate/camera debugging today.
2. Treat the screen integration as a separate firmware task.

Current limitation:

- The current repo does not yet contain a finished OLED/LCD node that polls the backend and renders `Welcome` / `Access Denied` independently.

## 4. Operator Checklist Before Hardware Testing

Run this checklist every time before a real test:

1. Backend is running and reachable from the hotspot/LAN.
2. Firestore `sensor_mac` and `camera_mac` match the real boards.
3. Cloud Vision API is enabled.
4. The admin dashboard is logged in and open.
5. The sensor node serial monitor shows `POST ... -> 202`.
6. The camera node serial monitor shows `No capture command available.` while idle and capture logs when commanded.

## 5. Practical Meaning of OFFLINE in the Dashboard

`OFFLINE` does not mean the spot is definitely free or definitely occupied.

It means:

- the backend has not received a fresh heartbeat recently
- the last known occupancy state is stale
- the operator should inspect power, Wi-Fi, or sensor wiring before trusting that spot
