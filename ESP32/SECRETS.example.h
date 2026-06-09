#ifndef PARKME_SECRETS_H
#define PARKME_SECRETS_H

// Copy this file to ESP32/SECRETS.h before flashing real boards.
constexpr char PARKME_WIFI_SSID[] = "YOUR_WIFI_OR_HOTSPOT";
constexpr char PARKME_WIFI_PASSWORD[] = "YOUR_WIFI_PASSWORD";

// Render/Railway example:
//   scheme = "https"
//   host   = "your-parkme-api.onrender.com"
//   port   = 443
constexpr char PARKME_SERVER_SCHEME[] = "https";
constexpr char PARKME_SERVER_HOST[] = "YOUR-CLOUD-BACKEND.onrender.com";
constexpr uint16_t PARKME_SERVER_PORT = 443;

// Leave empty for classroom/demo use. Set the same value as PARKME_HMAC_SECRET
// in the cloud backend if you later implement signed ESP32 requests.
constexpr char PARKME_HARDWARE_HMAC_SECRET[] = "";

constexpr char PARKME_API_UPDATE_SPOT_PATH[] = "/api/v1/sensors/heartbeat";
constexpr char PARKME_API_GATE_ENTRY_PATH[] = "/api/v1/sensors/park";

constexpr uint32_t PARKME_SENSOR_SPOT_ID = 101;
constexpr uint8_t PARKME_SENSOR_TRIG_PIN = 5;
constexpr uint8_t PARKME_SENSOR_ECHO_PIN = 18;
constexpr int8_t PARKME_SENSOR_BATTERY_PIN = 34;
constexpr int8_t PARKME_SENSOR_CALIBRATE_PIN = 0;

constexpr float PARKME_SENSOR_DEFAULT_BASELINE_CM = 80.0f;
constexpr float PARKME_SENSOR_OCCUPIED_DELTA_CM = 30.0f;
constexpr float PARKME_SENSOR_MIN_THRESHOLD_CM = 8.0f;
constexpr float PARKME_SENSOR_MAX_RELIABLE_DISTANCE_CM = 350.0f;
constexpr float PARKME_SENSOR_BATTERY_EMPTY_V = 3.20f;
constexpr float PARKME_SENSOR_BATTERY_FULL_V = 4.20f;
constexpr float PARKME_SENSOR_VOLTAGE_DIVIDER_RATIO = 2.0f;

constexpr uint32_t PARKME_SENSOR_SAMPLE_INTERVAL_MS = 1000;
constexpr uint32_t PARKME_SENSOR_HEARTBEAT_INTERVAL_MS = 360000;
constexpr uint32_t PARKME_SENSOR_WIFI_RETRY_INTERVAL_MS = 10000;
constexpr uint32_t PARKME_SENSOR_HTTP_TIMEOUT_MS = 5000;
constexpr bool PARKME_SENSOR_ALLOW_FREE_HEARTBEATS = true;

constexpr uint32_t PARKME_GATE_SPOT_ID = 201;
constexpr int8_t PARKME_GATE_TRIG_PIN = 12;
constexpr int8_t PARKME_GATE_ECHO_PIN = 13;
constexpr int8_t PARKME_GATE_FLASH_LED_PIN = 4;
constexpr int8_t PARKME_GATE_RELAY_PIN = -1;

constexpr uint8_t PARKME_GATE_LCD_SDA_PIN = 14;
constexpr uint8_t PARKME_GATE_LCD_SCL_PIN = 15;
constexpr uint8_t PARKME_GATE_LCD_ADDRESS = 0x27;
constexpr uint8_t PARKME_GATE_LCD_COLUMNS = 16;
constexpr uint8_t PARKME_GATE_LCD_ROWS = 2;

constexpr uint32_t PARKME_GATE_DEBOUNCE_MS = 250;
constexpr uint32_t PARKME_GATE_WIFI_RETRY_INTERVAL_MS = 10000;
constexpr uint32_t PARKME_GATE_HTTP_TIMEOUT_MS = 10000;
constexpr uint32_t PARKME_GATE_RELAY_PULSE_MS = 3000;

#endif
