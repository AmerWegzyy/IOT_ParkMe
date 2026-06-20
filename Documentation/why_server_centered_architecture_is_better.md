# Why A Server-Centered Architecture Is Better For ParkMe

This note is meant to explain, in practical project terms, why ParkMe should prefer a **server-centered architecture** over a **device-to-device architecture**.

The question is not whether direct communication between boards is possible. It is. The real question is which design is more stable, scalable, easier to debug, and easier to explain as a serious IoT system.

## Short Answer

For ParkMe, the better architecture is:

- `sensor -> server`
- `camera -> server`
- `screen -> server`
- `frontend -> server`

This is better than:

- `sensor -> camera`
- `camera -> screen`
- `sensor -> screen`
- plus a separate server on the side

## The Main Idea

Each parking spot should be treated as **one logical unit** by the backend, even if that spot contains several hardware devices.

For example, spot `C1` may contain:

- one ultrasonic sensor
- one camera
- one display

But the backend should think in terms of:

- `spot_id = C1`

not in terms of:

- "some random sensor MAC"
- "some random camera MAC"
- "some random display IP"

The hardware can be physically split into multiple boards, but the software model should stay unified.

## Why The Server-Centered Model Is Better

### 1. One Source Of Truth

The server is the single place that knows:

- which spot is occupied
- which camera belongs to which spot
- which sensor belongs to which spot
- whether the user is authorized
- whether the OCR succeeded
- whether the event is a violation
- what the display should show

If this logic is split across boards, then different devices can disagree about the state of the same parking spot.

### 2. Easier To Scale To More Spots

If ParkMe grows from 2 spots to 20 spots, a device-to-device design becomes hard to manage:

- boards must know each other's IP addresses
- IP addresses may change
- each board may need custom routing logic
- replacing one board may require reconfiguring several others

With a server-centered design, adding a new spot usually means:

1. create the new `parking_spots/<spot_id>` record
2. register the sensor, camera, and display identities
3. point all devices at the same backend URL

That is much cleaner.

### 3. Works Better In The Cloud

In a local hotspot, boards can sometimes talk directly to each other because they are on the same subnet.

In the cloud, that is much weaker:

- ESP devices are often behind NAT
- they usually do not have public IP addresses
- the server cannot reliably open direct connections back to them

The normal cloud-friendly pattern is:

- devices open outbound connections to the backend
- devices poll for commands or keep a persistent outbound connection

That makes the same logic work both:

- locally
- in Google Cloud

### 4. Easier To Debug

When the server is in the middle, all important events are visible in one place:

- heartbeats
- capture requests
- OCR results
- violations
- retries
- command acknowledgements

This makes debugging easier because you can inspect:

- backend logs
- Firestore state
- frontend state

If devices talk mostly to each other, then debugging becomes distributed and harder to follow.

### 5. Cleaner Responsibilities

In a good IoT architecture, edge devices should stay simple.

Suggested responsibilities:

- Sensor node: detect occupied/free and send telemetry
- Camera node: capture and upload a photo when commanded
- Screen node: ask the server what message to display
- Server: decide everything important

This is better than making the camera decide display behavior, or making the sensor coordinate the whole spot.

### 6. Better Fit For ParkMe's Existing Backend

ParkMe already has backend logic for:

- OCR
- RBAC / authorization
- ghost logs
- retries
- violation handling
- dashboard updates
- admin resolution flow

This means the project already benefits from central decision-making. Moving more logic into the server is consistent with the current system.

## What The Server Still Needs To Know

Even in a server-centered design, the backend still needs to know device identity.

That usually means:

- `spot_id`
- device role: `sensor`, `camera`, `display`
- device identity: MAC address or custom device ID

Important:

- MAC address is for **identification and validation**
- not for **internet routing**

The server should not depend on local private IP addresses of ESP boards in cloud deployment.

## Recommended Identity Model

The best pattern is:

- `spot_id` is the main business identity
- MAC address is a secondary technical identity

Example Firestore document:

```json
parking_spots/C1 {
  "sensor_mac": "A8:42:E3:46:F4:E0",
  "camera_mac": "24:6F:28:47:F9:E8",
  "display_id": "display-c1",
  "category": "student"
}
```

Example sensor payload:

```json
{
  "spot_id": "C1",
  "device_role": "sensor",
  "mac_address": "A8:42:E3:46:F4:E0",
  "is_occupied": true,
  "battery_level": 83
}
```

Example camera poll payload:

```json
{
  "spot_id": "C1",
  "device_role": "camera",
  "camera_mac": "24:6F:28:47:F9:E8"
}
```

This lets the backend validate that each device really belongs to the spot it claims.

## Localhost vs Cloud

### Local Testing

When testing on a laptop:

- the browser can use `http://127.0.0.1:8000`
- ESP boards cannot use `localhost`
- ESP boards must use the laptop's LAN IP, for example:
  - `http://172.20.10.8:8000`

### Cloud Deployment

When deployed to Google Cloud Run:

- all devices should call the cloud backend URL
- devices do not need to know each other's IPs
- devices do not need to expose local HTTP servers to the public internet

This is one of the strongest reasons to keep the server in the middle.

## What About Treating Each Spot As A Black Box?

That is a good idea, but it should be understood correctly.

Good meaning of "black box":

- each spot is a self-contained logical unit
- the server interacts with the spot through defined APIs
- the server does not care how many boards are physically inside the spot

Bad meaning of "black box":

- all logic is hidden inside the hardware
- devices coordinate among themselves
- the server only passively receives partial updates

For ParkMe, the first meaning is better.

So yes:

- each spot can be seen as a black box

But:

- the server should still coordinate the workflow for that spot

## Why Direct Device-To-Device Is Weaker

Direct board-to-board communication can work for a quick demo, but it has serious drawbacks:

- boards must know each other's IP addresses and ports
- IP addresses can change after reconnecting to Wi-Fi or hotspot
- logic gets scattered across devices
- it is harder to replace one board without affecting the others
- cloud deployment becomes much harder
- security and logging become weaker

This approach is fine for:

- temporary hacks
- offline lab experiments
- emergency demo workarounds

But it is not the stronger architecture for a growing IoT system.

## Final Recommendation

For ParkMe, the recommended architecture is:

1. The backend is the decision-making center.
2. Each parking spot is one logical unit identified by `spot_id`.
3. Each physical device reports to the backend using its device role and MAC/device ID.
4. Devices do not depend on each other's IPs.
5. The backend decides:
   - when the camera should capture
   - what the display should show
   - whether a parking event is valid, denied, unresolved, or aborted

## Final One-Sentence Summary

If ParkMe is meant to be a real IoT system and not just a temporary hardware demo, then the best design is:

**server-centered coordination with spot-based identity, while the hardware devices remain simple edge nodes.**
