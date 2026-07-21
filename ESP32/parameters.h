// ParkMe — Hard-Coded Parameters (reference)
// =============================================================================
// This file DOCUMENTS every compile-time (HARD CODED) parameter of the ParkMe
// firmware and what it does. Changing any of these requires re-flashing the
// board.
//
// The parameters are actually DEFINED in ESP32/SECRETS.h (created by copying
// ESP32/SECRETS.example.h). They live there because most of them sit next to
// the Wi-Fi/host secrets and are edited together when a board is provisioned.
// This file is a comment-only description so including it can never clash with
// those definitions — see SECRETS.example.h for the editable template.
//
// (Secrets themselves — Wi-Fi SSID/password, backend host — are listed in
//  SECRETS.example.h, not here.)
// =============================================================================
#ifndef PARKME_PARAMETERS_REFERENCE_H
#define PARKME_PARAMETERS_REFERENCE_H

// --- Sensor node: ultrasonic + button pins ----------------------------------
// PARKME_SENSOR_TRIG_PIN            GPIO 5  — HC-SR04 trigger (output)
// PARKME_SENSOR_ECHO_PIN           GPIO 18  — HC-SR04 echo (input)
// PARKME_SENSOR_BATTERY_PIN        GPIO 34  — optional battery-divider ADC (unused on USB build)
// PARKME_SENSOR_CALIBRATE_PIN      GPIO 13  — calibration push-button to GND (internal pull-up; 0 = reuse BOOT)

// --- Sensor node: occupancy detection thresholds (cm) ------------------------
// PARKME_SENSOR_OCCUPIED_THRESHOLD_CM     20   — default trigger distance until a technician calibrates
// PARKME_SENSOR_MIN_THRESHOLD_CM           3   — HC-SR04 cannot measure reliably below this
// PARKME_SENSOR_CALIBRATION_MARGIN_CM      2   — added to the demonstrated distance during calibration
// PARKME_SENSOR_CALIBRATION_MAX_TARGET_CM 50   — calibration fails if the target is farther than this
// PARKME_SENSOR_MAX_RELIABLE_DISTANCE_CM 350   — readings beyond this are treated as "no echo"
// PARKME_SENSOR_DEFAULT_BASELINE_CM       80   — legacy empty-spot baseline (superseded by calibration)
// PARKME_SENSOR_OCCUPIED_DELTA_CM         30   — legacy baseline delta (superseded by calibration)

// --- Sensor node: battery gauge (volts) --------------------------------------
// PARKME_SENSOR_BATTERY_EMPTY_V         3.20   — voltage reported as 0 %
// PARKME_SENSOR_BATTERY_FULL_V          4.20   — voltage reported as 100 %
// PARKME_SENSOR_VOLTAGE_DIVIDER_RATIO   2.0    — external divider ratio on the battery pin

// --- Sensor node: timing (ms) ------------------------------------------------
// PARKME_SENSOR_SAMPLE_INTERVAL_MS         500  — distance sampled 2×/second (3-sample average)
// PARKME_SENSOR_HEARTBEAT_INTERVAL_MS    20000  — heartbeat POST cadence (plus immediately on state change)
// PARKME_SENSOR_WIFI_RETRY_INTERVAL_MS   20000  — reconnect spacing (long, to keep ESP-NOW channel pinned)
// PARKME_SENSOR_HTTP_TIMEOUT_MS           5000  — heartbeat HTTP timeout (headroom for the Cloud Run TLS handshake)
// PARKME_SENSOR_ESPNOW_STATE_SYNC_INTERVAL_MS 2000 — re-broadcast OCCUPIED to the camera every 2 s
// PARKME_SENSOR_ALLOW_FREE_HEARTBEATS     true  — also send periodic heartbeats while the spot is free

// --- ESP-NOW peer ------------------------------------------------------------
// PARKME_CAMERA_ESPNOW_PEER_MAC  "24:6F:28:47:F9:E8" — camera board STA MAC the sensor triggers

// --- Camera / gate node ------------------------------------------------------
// PARKME_GATE_SPOT_ID            "C1"   — MUST match a Firestore parking_spots document id
// PARKME_GATE_FLASH_LED_PIN         4   — onboard flash LED, fired during capture
// PARKME_GATE_RELAY_PIN            -1   — optional gate relay (-1 = disabled)
// PARKME_GATE_WIFI_RETRY_INTERVAL_MS 20000 — reconnect spacing (keeps ESP-NOW channel pinned)
// PARKME_GATE_HTTP_TIMEOUT_MS     25000 — /park response timeout (server runs Vision OCR + Firestore)
// PARKME_GATE_MAX_CAPTURE_RETRIES     1 — capture attempts per occupancy cycle

// --- Sensor-node OLED display (SSD1306, I2C) ---------------------------------
// PARKME_DISPLAY_SDA_PIN          21    — I2C data
// PARKME_DISPLAY_SCL_PIN          22    — I2C clock
// PARKME_DISPLAY_I2C_ADDRESS      0x3C  — SSD1306 address
// PARKME_DISPLAY_COLUMN_OFFSET     2    — horizontal pixel offset (set 0 or 2 if text is shifted)
// PARKME_DISPLAY_COMMAND_POLL_INTERVAL_MS 750 — how often the sensor polls for screen commands (SSE fallback)

#endif  // PARKME_PARAMETERS_REFERENCE_H
