#include "esp_camera.h"

#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <Wire.h>

#include <ParkMeCommon.h>
#include <ParkMeConfig.h>
#include <ParkMeLcd.h>

using namespace parkme;

// AI Thinker ESP32-CAM pins
#define PWDN_GPIO_NUM 32
#define RESET_GPIO_NUM -1
#define XCLK_GPIO_NUM 0
#define SIOD_GPIO_NUM 26
#define SIOC_GPIO_NUM 27
#define Y9_GPIO_NUM 35
#define Y8_GPIO_NUM 34
#define Y7_GPIO_NUM 39
#define Y6_GPIO_NUM 36
#define Y5_GPIO_NUM 21
#define Y4_GPIO_NUM 19
#define Y3_GPIO_NUM 18
#define Y2_GPIO_NUM 5
#define VSYNC_GPIO_NUM 25
#define HREF_GPIO_NUM 23
#define PCLK_GPIO_NUM 22

namespace {

ParkMeLcd lcd(PARKME_GATE_LCD_ADDRESS,
              PARKME_GATE_LCD_COLUMNS,
              PARKME_GATE_LCD_ROWS);

unsigned long lastWifiAttemptAtMs = 0;
bool carPresent = false;

}  // namespace

float readDistanceCm() {
  digitalWrite(PARKME_GATE_TRIG_PIN, LOW);
  delayMicroseconds(2);

  digitalWrite(PARKME_GATE_TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(PARKME_GATE_TRIG_PIN, LOW);

  long durationUs = pulseIn(PARKME_GATE_ECHO_PIN, HIGH, 30000);
  if (durationUs == 0) {
    return -1.0f;
  }

  return (durationUs * 0.0343f) / 2.0f;
}

void showScreen(const String &line1, const String &line2) {
  lcd.printAt(0, fitForLcd(line1, PARKME_GATE_LCD_COLUMNS));
  lcd.printAt(1, fitForLcd(line2, PARKME_GATE_LCD_COLUMNS));
}

void pulseGateRelay() {
  if (PARKME_GATE_RELAY_PIN < 0) {
    return;
  }

  digitalWrite(PARKME_GATE_RELAY_PIN, HIGH);
  delay(PARKME_GATE_RELAY_PULSE_MS);
  digitalWrite(PARKME_GATE_RELAY_PIN, LOW);
}

bool connectWiFi() {
  lastWifiAttemptAtMs = millis();

  showScreen("Connecting WiFi", "Please wait...");
  WiFi.begin(PARKME_WIFI_SSID, PARKME_WIFI_PASSWORD);

  unsigned long startedAtMs = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - startedAtMs < 12000) {
    delay(400);
  }

  if (WiFi.status() == WL_CONNECTED) {
    showScreen("WiFi connected", "Ready to scan");
    Serial.print("WiFi connected. IP: ");
    Serial.println(WiFi.localIP());
    return true;
  }

  showScreen("WiFi failed", "Retry later");
  Serial.println("WiFi connection failed.");
  return false;
}

void maintainWiFi() {
  if (WiFi.status() == WL_CONNECTED) {
    return;
  }

  if (millis() - lastWifiAttemptAtMs >= PARKME_GATE_WIFI_RETRY_INTERVAL_MS) {
    connectWiFi();
  }
}

bool initCamera() {
  camera_config_t config = {};
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sscb_sda = SIOD_GPIO_NUM;
  config.pin_sscb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;
  config.frame_size = psramFound() ? FRAMESIZE_VGA : FRAMESIZE_QVGA;
  config.jpeg_quality = psramFound() ? 10 : 12;
  config.fb_count = psramFound() ? 2 : 1;

  esp_err_t status = esp_camera_init(&config);
  if (status != ESP_OK) {
    Serial.printf("Camera init failed: 0x%x\n", status);
    showScreen("Camera failed", "Check wiring");
    return false;
  }

  return true;
}

bool captureAndUpload(String &responseBody, int &httpStatusCode) {
  camera_fb_t *frame = nullptr;

  if (PARKME_GATE_FLASH_LED_PIN >= 0) {
    digitalWrite(PARKME_GATE_FLASH_LED_PIN, HIGH);
    delay(80);
  }

  frame = esp_camera_fb_get();

  if (PARKME_GATE_FLASH_LED_PIN >= 0) {
    digitalWrite(PARKME_GATE_FLASH_LED_PIN, LOW);
  }

  if (!frame) {
    Serial.println("Camera capture failed.");
    return false;
  }

  WiFiClient plainClient;
  WiFiClientSecure secureClient;
  Client *client =
      String(PARKME_SERVER_SCHEME) == "https" ? &secureClient : &plainClient;
  secureClient.setInsecure();
  client->setTimeout(PARKME_GATE_HTTP_TIMEOUT_MS);

  if (!client->connect(PARKME_SERVER_HOST, PARKME_SERVER_PORT)) {
    esp_camera_fb_return(frame);
    Serial.println("Cannot connect to backend.");
    return false;
  }

  const String boundary = "----ParkMeBoundary7MA4YWxkTrZu0gW";
  String part1 = "--" + boundary +
                 "\r\nContent-Disposition: form-data; name=\"camera_mac\"\r\n\r\n" +
                 WiFi.macAddress() + "\r\n";
  String part2 = "--" + boundary +
                 "\r\nContent-Disposition: form-data; name=\"file\"; filename=\"capture.jpg\"\r\n"
                 "Content-Type: image/jpeg\r\n\r\n";
  String closing = "\r\n--" + boundary + "--\r\n";

  size_t contentLength =
      part1.length() + part2.length() + frame->len + closing.length();

  client->print(String("POST ") + PARKME_API_GATE_ENTRY_PATH + " HTTP/1.1\r\n");
  client->print(String("Host: ") + PARKME_SERVER_HOST + "\r\n");
  client->print("Connection: close\r\n");
  client->print("Content-Type: multipart/form-data; boundary=" + boundary +
               "\r\n");
  client->print("Content-Length: " + String(contentLength) + "\r\n\r\n");
  client->print(part1);
  client->print(part2);
  client->write(frame->buf, frame->len);
  client->print(closing);

  esp_camera_fb_return(frame);

  unsigned long waitStartedAtMs = millis();
  while (!client->available() && client->connected() &&
         millis() - waitStartedAtMs < PARKME_GATE_HTTP_TIMEOUT_MS) {
    delay(10);
  }

  if (!client->available()) {
    client->stop();
    Serial.println("Backend response timeout.");
    return false;
  }

  String statusLine = client->readStringUntil('\n');
  httpStatusCode = parseHttpStatusCode(statusLine);

  while (client->connected()) {
    String headerLine = client->readStringUntil('\n');
    if (headerLine == "\r") {
      break;
    }
  }

  responseBody = client->readString();
  client->stop();

  Serial.print("HTTP ");
  Serial.print(httpStatusCode);
  Serial.print(" | ");
  Serial.println(responseBody);

  return true;
}

GateAction handleServerDecision(const String &responseBody) {
  GateAction action = parseGateAction(responseBody.c_str());
  String message = extractJsonStringField(responseBody, "message");

  switch (action) {
    case ACTION_WELCOME:
      showScreen("Access granted", fitForLcd(message, PARKME_GATE_LCD_COLUMNS));
      pulseGateRelay();
      delay(2500);
      break;
    case ACTION_DENIED:
      showScreen("Access denied", fitForLcd(message, PARKME_GATE_LCD_COLUMNS));
      delay(2500);
      break;
    case ACTION_RETRY:
      showScreen("Scan again", fitForLcd(message, PARKME_GATE_LCD_COLUMNS));
      delay(2000);
      break;
    default:
      showScreen("Server error", "Unexpected data");
      delay(2000);
      break;
  }

  return action;
}

GateAction performGateScan() {
  if (WiFi.status() != WL_CONNECTED) {
    showScreen("WiFi offline", "Cannot scan");
    delay(1500);
    return ACTION_UNKNOWN;
  }

  showScreen("Capturing...", "Hold still");

  String responseBody;
  int httpStatusCode = -1;

  if (!captureAndUpload(responseBody, httpStatusCode)) {
    showScreen("Upload failed", "Try again");
    delay(2000);
    return ACTION_RETRY;
  }

  if (httpStatusCode < 200 || httpStatusCode >= 300) {
    showScreen("Server rejected", "Check backend");
    delay(2000);
    return ACTION_RETRY;
  }

  return handleServerDecision(responseBody);
}

bool isCarAtGate() {
  float distanceCm = readDistanceCm();
  return (distanceCm > 0 && distanceCm <= 20.0f);
}

void setup() {
  Serial.begin(115200);
  delay(200);

  if (PARKME_GATE_TRIG_PIN >= 0) {
    pinMode(PARKME_GATE_TRIG_PIN, OUTPUT);
  }
  if (PARKME_GATE_ECHO_PIN >= 0) {
    pinMode(PARKME_GATE_ECHO_PIN, INPUT);
  }

  if (PARKME_GATE_FLASH_LED_PIN >= 0) {
    pinMode(PARKME_GATE_FLASH_LED_PIN, OUTPUT);
    digitalWrite(PARKME_GATE_FLASH_LED_PIN, LOW);
  }

  if (PARKME_GATE_RELAY_PIN >= 0) {
    pinMode(PARKME_GATE_RELAY_PIN, OUTPUT);
    digitalWrite(PARKME_GATE_RELAY_PIN, LOW);
  }

  Wire.begin(PARKME_GATE_LCD_SDA_PIN, PARKME_GATE_LCD_SCL_PIN);
  lcd.begin(Wire);
  lcd.backlight(true);
  showScreen("ParkMe Gate", "Booting...");

  if (!initCamera()) {
    return;
  }

  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  connectWiFi();
  showScreen("Ready to scan", "Approach gate");
}

void loop() {
  maintainWiFi();

  bool carCurrentlyDetected = isCarAtGate();

  if (carCurrentlyDetected && !carPresent) {
    carPresent = true;
    int retries = 0;
    
    while (retries < 3) {
      GateAction result = performGateScan();
      
      if (result == ACTION_WELCOME || result == ACTION_DENIED) {
        break; 
      }
      
      if (result == ACTION_RETRY || result == ACTION_UNKNOWN) {
        retries++;
        if (retries < 3) {
          showScreen("Retrying...", String(retries) + "/3");
          delay(1000); // brief pause before retry
        }
      }
    }
    
    showScreen("Please", "Clear gate");
  } else if (!carCurrentlyDetected && carPresent) {
    carPresent = false;
    showScreen("Ready to scan", "Approach gate");
  }
}
