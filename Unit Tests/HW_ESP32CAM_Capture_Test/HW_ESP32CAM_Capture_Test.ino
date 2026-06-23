#include "esp_camera.h"

#include <Arduino.h>
#include <WiFi.h>

// AI Thinker ESP32-CAM pins.
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

// Fill these with the same Wi-Fi values you use in ESP32/SECRETS.h.
// Kept local so Arduino IDE can open this HW test directly from Unit Tests.
constexpr char PARKME_WIFI_SSID[] = "George";
constexpr char PARKME_WIFI_PASSWORD[] = "george2003";

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
  config.frame_size = FRAMESIZE_QVGA;
  config.jpeg_quality = 12;
  config.fb_count = psramFound() ? 2 : 1;

  esp_err_t status = esp_camera_init(&config);
  if (status != ESP_OK) {
    Serial.printf("FAIL - camera init failed: 0x%x\n", status);
    return false;
  }

  Serial.println("PASS - camera init succeeded");
  return true;
}

void connectWiFiForIpCheck() {
  Serial.print("Connecting to WiFi: ");
  Serial.println(PARKME_WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(PARKME_WIFI_SSID, PARKME_WIFI_PASSWORD);

  unsigned long startedAtMs = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - startedAtMs < 12000) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("PASS - WiFi connected. IP: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("FAIL - WiFi did not connect within 12 seconds");
  }
}

void captureFrameTest() {
  camera_fb_t *frame = esp_camera_fb_get();
  if (!frame) {
    Serial.println("FAIL - camera capture returned no frame");
    return;
  }

  Serial.print("PASS - captured JPEG frame, bytes: ");
  Serial.println(frame->len);
  esp_camera_fb_return(frame);
}

}  // namespace

void setup() {
  Serial.begin(115200);
  delay(1500);
  Serial.println();
  Serial.println("HW TEST: AI Thinker ESP32-CAM OV2640 capture");

  bool cameraReady = initCamera();
  connectWiFiForIpCheck();

  if (cameraReady) {
    captureFrameTest();
  }
}

void loop() {
  delay(5000);
  captureFrameTest();
}
