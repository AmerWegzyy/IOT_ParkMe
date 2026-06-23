## ParkMe Arduino firmware

This folder now contains two main Arduino deliverables:

- `ParkMeSensorNode`: ultrasonic parking node that calibrates an empty-spot baseline, detects occupied/free state, reads battery level, posts telemetry to the FastAPI backend, and renders backend-driven screen messages on the same ESP32.
- `ParkMeCameraNode`: ESP32-CAM gate node that polls the backend for capture commands, captures a photo, and uploads it to the backend.
- `ParkMeFirmwareCompileTests`: compile-time unit tests for the shared decision logic used by both sketches.

Shared files:

- `SECRETS.h`: Wi-Fi, backend host, pins, and timing values.
- `ParkMeCommon/ParkMeCommon.h`: reusable logic for thresholds, battery percent, heartbeats, and backend response parsing.
- `ParkMeLcd/ParkMeLcd.h`: legacy lightweight I2C LCD driver from the earlier camera-screen design.

Before flashing:

1. Edit `SECRETS.h`.
2. For the sensor node, leave the spot empty and hold the calibration button during boot to store a baseline distance.
3. For the sensor+screen node, confirm the display ID and I2C pins in `SECRETS.h`.
4. The sensor sketch now uses the same low-level OLED style as `Unit Tests/HW_OLED_SSD1306_I2C_Test`. If text is shifted, adjust `PARKME_DISPLAY_COLUMN_OFFSET` in `SECRETS.h` between `0` and `2`.
