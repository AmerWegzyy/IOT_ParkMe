#ifndef PARKME_SECRETS_H
#define PARKME_SECRETS_H

// Copy this file to ESP32/SECRETS.h before flashing real boards.
constexpr char PARKME_WIFI_SSID[] = "YOUR_WIFI_OR_HOTSPOT";
constexpr char PARKME_WIFI_PASSWORD[] = "YOUR_WIFI_PASSWORD";

// Cloud Run example:
//   scheme = "https"
//   host   = "your-parkme-backend-xxxxxx-xx.a.run.app"
//   port   = 443
constexpr char PARKME_SERVER_SCHEME[] = "https";
constexpr char PARKME_SERVER_HOST[] = "YOUR-CLOUD-RUN-HOST.a.run.app";
constexpr uint16_t PARKME_SERVER_PORT = 443;


constexpr char PARKME_API_UPDATE_SPOT_PATH[] = "/api/v1/sensors/heartbeat";
constexpr char PARKME_API_GATE_ENTRY_PATH[] = "/api/v1/sensors/park";
constexpr char PARKME_API_DISPLAY_POLL_PATH[] = "/api/v1/displays/poll";
constexpr char PARKME_API_DISPLAY_RESULT_PATH[] = "/api/v1/displays/result";

constexpr uint8_t PARKME_SENSOR_TRIG_PIN = 5;
constexpr uint8_t PARKME_SENSOR_ECHO_PIN = 18;
constexpr int8_t PARKME_SENSOR_BATTERY_PIN = 34;
constexpr int8_t PARKME_SENSOR_CALIBRATE_PIN = 0;

constexpr float PARKME_SENSOR_DEFAULT_BASELINE_CM = 80.0f;
constexpr float PARKME_SENSOR_OCCUPIED_DELTA_CM = 30.0f;
constexpr float PARKME_SENSOR_OCCUPIED_THRESHOLD_CM = 20.0f;
constexpr float PARKME_SENSOR_MIN_THRESHOLD_CM = 8.0f;
constexpr float PARKME_SENSOR_MAX_RELIABLE_DISTANCE_CM = 350.0f;
constexpr float PARKME_SENSOR_BATTERY_EMPTY_V = 3.20f;
constexpr float PARKME_SENSOR_BATTERY_FULL_V = 4.20f;
constexpr float PARKME_SENSOR_VOLTAGE_DIVIDER_RATIO = 2.0f;

constexpr uint32_t PARKME_SENSOR_SAMPLE_INTERVAL_MS = 500;
constexpr uint32_t PARKME_SENSOR_HEARTBEAT_INTERVAL_MS = 20000;
constexpr uint32_t PARKME_SENSOR_WIFI_RETRY_INTERVAL_MS = 5000;
constexpr uint32_t PARKME_SENSOR_HTTP_TIMEOUT_MS = 2500;
constexpr bool PARKME_SENSOR_ALLOW_FREE_HEARTBEATS = true;
// Set this to the camera board STA MAC address to enable direct ESP-NOW
// sensor -> camera coordination.
constexpr char PARKME_CAMERA_ESPNOW_PEER_MAC[] = "";
constexpr uint32_t PARKME_SENSOR_ESPNOW_STATE_SYNC_INTERVAL_MS = 2000;

// Must match an actual Firestore parking_spots document ID.
constexpr char PARKME_GATE_SPOT_ID[] = "C1";
constexpr int8_t PARKME_GATE_TRIG_PIN = 12;
constexpr int8_t PARKME_GATE_ECHO_PIN = 13;
constexpr int8_t PARKME_GATE_FLASH_LED_PIN = 4;
constexpr int8_t PARKME_GATE_RELAY_PIN = -1;
constexpr float PARKME_GATE_TRIGGER_DISTANCE_CM = 50.0f;

// Many I2C LCD backpacks label the clock pin "SCK"; that pin should connect
// to the ESP32's configured SCL pin below.
constexpr uint8_t PARKME_GATE_LCD_SDA_PIN = 14;
constexpr uint8_t PARKME_GATE_LCD_SCL_PIN = 15;
constexpr uint8_t PARKME_GATE_LCD_ADDRESS = 0x27;
constexpr uint8_t PARKME_GATE_LCD_COLUMNS = 16;
constexpr uint8_t PARKME_GATE_LCD_ROWS = 2;

constexpr uint32_t PARKME_GATE_DEBOUNCE_MS = 250;
constexpr uint32_t PARKME_GATE_WIFI_RETRY_INTERVAL_MS = 5000;
constexpr uint32_t PARKME_GATE_HTTP_TIMEOUT_MS = 7000;
constexpr uint32_t PARKME_GATE_COMMAND_POLL_INTERVAL_MS = 0;
constexpr uint8_t PARKME_GATE_MAX_CAPTURE_RETRIES = 1;
constexpr uint32_t PARKME_GATE_RETRY_STATUS_MS = 1200;
constexpr uint32_t PARKME_GATE_RETRY_BACKOFF_MS = 0;
constexpr uint32_t PARKME_GATE_RELAY_PULSE_MS = 3000;
constexpr bool PARKME_GATE_ENABLE_SERVER_POLL_FALLBACK = false;

// Sensor-board display settings. The same ESP32 that reads the ultrasonic
// sensor also polls the backend for user-facing screen messages.
constexpr char PARKME_DISPLAY_ID[] = "display-c1";
constexpr bool PARKME_DISPLAY_ENABLE_GRAPHICS = true;
constexpr uint8_t PARKME_DISPLAY_SDA_PIN = 21;
constexpr uint8_t PARKME_DISPLAY_SCL_PIN = 22;
constexpr uint8_t PARKME_DISPLAY_I2C_ADDRESS = 0x3C;
constexpr uint8_t PARKME_DISPLAY_COLUMN_OFFSET = 2;
constexpr uint32_t PARKME_DISPLAY_WIFI_RETRY_INTERVAL_MS = 5000;
constexpr uint32_t PARKME_DISPLAY_HTTP_TIMEOUT_MS = 1200;
constexpr uint32_t PARKME_DISPLAY_COMMAND_POLL_INTERVAL_MS = 750;
constexpr uint32_t PARKME_DISPLAY_CAMERA_QUEUED_HOLD_MS = 800;
constexpr uint32_t PARKME_DISPLAY_CAMERA_STARTED_HOLD_MS = 1800;
constexpr uint32_t PARKME_DISPLAY_CAMERA_COMPLETED_HOLD_MS = 1200;
constexpr uint32_t PARKME_DISPLAY_CAMERA_FAILED_HOLD_MS = 2500;

#endif
