# ParkMe - Hardware Unit Tests Report

Project name: ParkMe

Group number: Fill in your group number

## Hardware Unit Tests

| # | Hardware name | Test results | Test code filename in git repo - UNIT TESTS sub folder | Reference for test code |
|---|---|---|---|---|
| 1 | HC-SR04 ultrasonic distance sensor | Reads average distance in cm and prints `PASS` when echo readings are valid. You manually tested the sensor before; run this sketch and record measured distances for empty/occupied parking states. | `Unit Tests/HW_Ultrasonic_Distance_Test/HW_Ultrasonic_Distance_Test.ino` | Based on Arduino `pulseIn()` ultrasonic timing formula and ParkMe threshold logic in `ParkMeCommon.h`. |
| 2 | ESP32-CAM AI Thinker with OV2640 camera | Camera was connected to Wi-Fi and pictures were taken successfully. Test sketch prints `PASS` for camera init, Wi-Fi connection/IP, and JPEG frame capture. | `Unit Tests/HW_ESP32CAM_Capture_Test/HW_ESP32CAM_Capture_Test.ino` | Based on Espressif/Arduino ESP32 CameraWebServer example and `esp_camera_fb_get()`. |
| 3 | 0.96 inch I2C OLED SSD1306 display | Test sketch checks the configured I2C address, initializes the OLED, and keeps `WELCOME` / `PARKME` on the screen. Fill the final result after physically running it. | `Unit Tests/HW_OLED_SSD1306_I2C_Test/HW_OLED_SSD1306_I2C_Test.ino` | Based on Adafruit SSD1306, Adafruit GFX, and Arduino `Wire` libraries. |

## How To Record Evidence

For each hardware test:

1. Open the matching `.ino` file in Arduino IDE.
2. Select the correct board and port.
3. Upload the sketch.
4. Open Serial Monitor at `115200 baud`.
5. Copy or screenshot the `PASS` / `FAIL` lines.
6. For the OLED test, also take a photo of the OLED showing `WELCOME`.
7. For the camera test, also keep a screenshot/photo from the camera web page or capture result.

## Expected Serial Monitor Examples

Ultrasonic:

```text
HW TEST: HC-SR04 ultrasonic distance sensor
Distance average: 78.31 cm | Threshold: 50.00 cm | Result: PASS - sensor is reading, classified as FREE
Distance average: 22.44 cm | Threshold: 50.00 cm | Result: PASS - sensor is reading, classified as OCCUPIED
```

ESP32-CAM:

```text
HW TEST: AI Thinker ESP32-CAM OV2640 capture
PASS - camera init succeeded
PASS - WiFi connected. IP: 172.20.10.2
PASS - captured JPEG frame, bytes: 18432
```

OLED:

```text
HW TEST: I2C OLED SSD1306 display
PASS - OLED I2C address responded
PASS - OLED initialized and WELCOME text displayed
```
