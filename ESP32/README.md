## ParkMe Arduino firmware

**Wiring diagram** (all pins as configured in `SECRETS.h`):

![ParkMe wiring diagram](../Documentation/images/wiring_diagram.png)

Sensor node connections: HC-SR04 → VIN(5V)/GND, TRIG=GPIO5, ECHO=GPIO18 · OLED SSD1306 → 3V3/GND, SCL=GPIO22, SDA=GPIO21 (I2C 0x3C) · calibration button GPIO13→GND (internal pull-up, no resistor). Camera node needs only 5V+GND — camera and flash LED are onboard (IO0→GND only while flashing). Editable source: `../Documentation/images/wiring_diagram.svg`.

This folder now contains two main Arduino deliverables:

- `ParkMeSensorNode`: ultrasonic parking node that calibrates an empty-spot baseline, detects occupied/free state, reads battery level, posts telemetry to the FastAPI backend, and renders backend-driven screen messages on the same ESP32.
- `ParkMeCameraNode`: ESP32-CAM gate node that receives direct occupancy triggers over ESP-NOW, performs a single immediate capture/upload for each occupied cycle, and then waits for the spot to become free before it can capture again.
- `ParkMeFirmwareCompileTests`: compile-time unit tests for the shared decision logic used by both sketches.

Shared files:

- `SECRETS.h`: Wi-Fi, backend host, pins, and timing values.
- `ParkMeCommon/ParkMeCommon.h`: reusable logic for thresholds, battery percent, heartbeats, and backend response parsing.
- `ParkMeLcd/ParkMeLcd.h`: legacy lightweight I2C LCD driver from the earlier camera-screen design.

Before flashing:

1. Edit `SECRETS.h`.
   Set `PARKME_CAMERA_ESPNOW_PEER_MAC` on the sensor board to the ESP32-CAM STA MAC address if you want direct board-to-board triggering.
2. For the sensor node, calibrate the trigger distance: place an object at the exact distance where a car should be detected (3–50 cm), then hold the calibration button for 4 seconds while the node is running. The node averages 15 measurements of the target, adds a 2 cm margin, stores the result in flash as this node's occupied threshold, and shows CALIBRATE PASS/FAIL (with the new trigger value) on the OLED. Recalibrate any time the same way — no re-flash needed.
3. For the sensor+screen node, confirm the display ID and I2C pins in `SECRETS.h`.
4. The sensor sketch now uses the same low-level OLED style as `Unit Tests/HW_OLED_SSD1306_I2C_Test`. If text is shifted, adjust `PARKME_DISPLAY_COLUMN_OFFSET` in `SECRETS.h` between `0` and `2`.

