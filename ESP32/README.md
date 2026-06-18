## ParkMe Arduino firmware

This folder now contains three Arduino deliverables:

- `ParkMeSensorNode`: ultrasonic parking node that calibrates an empty-spot baseline, detects occupied/free state, reads battery level, and posts telemetry to the FastAPI backend.
- `ParkMeCameraNode`: ESP32-CAM gate node that captures a photo, uploads it to the backend, and shows `Access granted` or `Access denied` on a 16x2 I2C LCD.
- `ParkMeFirmwareCompileTests`: compile-time unit tests for the shared decision logic used by both sketches.

Shared files:

- `SECRETS.h`: Wi-Fi, backend host, pins, and timing values.
- `ParkMeCommon/ParkMeCommon.h`: reusable logic for thresholds, battery percent, heartbeats, and backend response parsing.
- `ParkMeLcd/ParkMeLcd.h`: lightweight I2C LCD driver so you do not need a third-party LCD library.

Before flashing:

1. Edit `SECRETS.h`.
2. Confirm the LCD uses address `0x27`; change it if your module uses a different address.
3. For the sensor node, leave the spot empty and hold the calibration button during boot to store a baseline distance.
