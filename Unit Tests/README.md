# ParkMe - Unit Tests & Validation Suites

This folder contains the complete verification suite for the **ParkMe** IoT smart parking system. It is organized into two primary categories:
1. **Hardware Validation Sketches (`HW_*`)**: Standalone Arduino/ESP32 bring-up sketches used to isolate, test, and verify physical sensors and actuators before running the main firmware.
2. **Software & Vision API Test Suite (`vision_api_tests/`)**: Python unit tests and end-to-end integration scripts verifying backend parking logic, multi-spot concurrency, and the Google Cloud Vision OCR license plate recognition (LPR) pipeline.

---

## Directory Structure

```text
Unit Tests/
├── HARDWARE_UNIT_TESTS_REPORT.md       # Summary table and submission report for hardware verification
├── README.md                           # This guide
├── HW_OLED_SSD1306_I2C_Test/           # 0.96" I2C OLED display verification sketch
│   └── HW_OLED_SSD1306_I2C_Test.ino
├── HW_Ultrasonic_Distance_Test/        # HC-SR04 ultrasonic sensor verification sketch
│   └── HW_Ultrasonic_Distance_Test.ino
├── HW_ESP32CAM_Capture_Test/           # AI Thinker ESP32-CAM camera & Wi-Fi upload verification sketch
│   └── HW_ESP32CAM_Capture_Test.ino
└── vision_api_tests/                   # Python software validation suite (LPR, OCR, Concurrency)
    ├── test_lpr_pipeline.py            # End-to-end OCR pipeline validation against test images
    ├── test_parallel_spots.py          # Concurrency and simultaneous multi-spot upload validation
    ├── test_backend_parking_logic.py   # Unit tests for timestamp & session preservation logic
    ├── test_plate_extraction.py        # Unit tests for OCR string cleaning & plate regex
    ├── TEST_SUMMARY.md                 # Detailed methodology & execution documentation
    ├── test_pics/                      # Real camera capture dataset (36 test images)
    ├── lpr_test_results.log            # Automated report output for LPR accuracy
    └── parallel_test_results.log       # Automated report output for backend parallelism
```

---

## 1. Hardware Unit Tests (`HW_*`)

Each hardware folder contains a standalone sketch (`.ino`) that can be opened directly in the **Arduino IDE** or **PlatformIO**. These tests require no external server dependency and output diagnostic verification lines to the **Serial Monitor at `115200 baud`**.

### A. OLED Display Test (`HW_OLED_SSD1306_I2C_Test`)
Verifies I2C communication and display initialization for the `0.96" SSD1306` display used on the entrance/exit gate node.

* **File:** `Unit Tests/HW_OLED_SSD1306_I2C_Test/HW_OLED_SSD1306_I2C_Test.ino`
* **Wiring (ESP32 DevKit):**
  ```text
  OLED VCC -> 3V3
  OLED GND -> GND
  OLED SDA -> GPIO21
  OLED SCK -> GPIO22
  ```
* **Expected Serial Monitor Output (`115200 baud`):**
  ```text
  HW TEST: I2C OLED SSD1306 display
  PASS - OLED I2C address responded
  PASS - OLED initialized and WELCOME text displayed
  ```
* **Expected Physical Display Output:**
  ```text
  WELCOME
  PARKME
  ```

### B. Ultrasonic Distance Sensor Test (`HW_Ultrasonic_Distance_Test`)
Verifies acoustic ping timing (`pulseIn`), median filtering across 10 samples, and threshold state classification (`FREE` vs `OCCUPIED`) for the `HC-SR04` ultrasonic sensor.

* **File:** `Unit Tests/HW_Ultrasonic_Distance_Test/HW_Ultrasonic_Distance_Test.ino`
* **Wiring (ESP32 Sensor Node):**
  ```text
  HC-SR04 VCC  -> 5V (or 3V3 depending on module variant)
  HC-SR04 GND  -> GND
  HC-SR04 TRIG -> GPIO5
  HC-SR04 ECHO -> GPIO18 (via voltage divider if 5V module)
  ```
* **Expected Serial Monitor Output (`115200 baud`):**
  ```text
  HW TEST: HC-SR04 ultrasonic distance sensor
  Distance average: 78.31 cm | Threshold: 50.00 cm | Result: PASS - sensor is reading, classified as FREE
  Distance average: 22.44 cm | Threshold: 50.00 cm | Result: PASS - sensor is reading, classified as OCCUPIED
  ```

### C. ESP32-CAM AI Thinker Capture Test (`HW_ESP32CAM_Capture_Test`)
Verifies OV2640 camera sensor pin assignments, frame buffer initialization (`esp_camera_fb_get`), Wi-Fi connectivity, and JPEG image capture integrity.

* **File:** `Unit Tests/HW_ESP32CAM_Capture_Test/HW_ESP32CAM_Capture_Test.ino`
* **Board Target:** `AI Thinker ESP32-CAM`
* **Expected Serial Monitor Output (`115200 baud`):**
  ```text
  HW TEST: AI Thinker ESP32-CAM OV2640 capture
  PASS - camera init succeeded
  PASS - WiFi connected. IP: 172.20.10.2
  PASS - captured JPEG frame, bytes: 18432
  ```

---

## 2. Software & Vision API Test Suite (`vision_api_tests/`)

The `vision_api_tests/` subdirectory contains Python suites for validating the FastAPI backend, parking business logic, and Google Cloud Vision AI integration.

### Prerequisites
Run from the root workspace directory with Python 3.11+ and backend dependencies installed:
```bash
pip install -r Backend/requirements.txt
```

### A. License Plate Recognition (LPR) Pipeline (`test_lpr_pipeline.py`)
Runs automated OCR extraction against real parking captures in `vision_api_tests/test_pics/`, verifying plate formatting, regex cleaning, and accuracy against ground truth filenames.

* **Run against local server:**
  ```bash
  python3 "Unit Tests/vision_api_tests/test_lpr_pipeline.py" --server-url http://127.0.0.1:8000
  ```
* **Run against live Cloud Run production backend:**
  ```bash
  python3 "Unit Tests/vision_api_tests/test_lpr_pipeline.py" --server-url https://parkme-backend-31114651685.me-west1.run.app
  ```

### B. Concurrency & Parallelism (`test_parallel_spots.py`)
Simulates simultaneous multi-spot uploads across spots (`A1`, `A2`, `B1`, `B2`, `C2`) using thread pools to ensure zero database cross-talk, race conditions, or state corruption under heavy load.

* **Execution:**
  ```bash
  python3 "Unit Tests/vision_api_tests/test_parallel_spots.py" --server-url https://parkme-backend-31114651685.me-west1.run.app
  ```

### C. Core Logic Unit Tests
Executes offline deterministic unit tests against core backend helper functions:
```bash
# Test OCR string normalization and plate number regex rules
python3 -m unittest "Unit Tests/vision_api_tests/test_plate_extraction.py"

# Test active parking log retention, expiration, and timestamp math
python3 -m unittest "Unit Tests/vision_api_tests/test_backend_parking_logic.py"
```

---

## 3. Reporting and Documentation

* For the official academic hardware verification report, refer to [HARDWARE_UNIT_TESTS_REPORT.md](HARDWARE_UNIT_TESTS_REPORT.md).
* For detailed breakdown of backend test metrics and accuracy targets, refer to [vision_api_tests/TEST_SUMMARY.md](vision_api_tests/TEST_SUMMARY.md).
