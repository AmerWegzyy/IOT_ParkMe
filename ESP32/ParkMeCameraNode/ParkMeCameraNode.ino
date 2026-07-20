#include "esp_camera.h"

#include <esp_now.h>
#include <esp_wifi.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>

#include "ParkMeCommon.h"
#include "ParkMeConfig.h"

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

unsigned long lastWifiAttemptAtMs = 0;
bool espNowReady = false;
// ESP-NOW only works when both boards' radios are on the SAME 2.4 GHz
// channel. While associated to the AP that is guaranteed; during an outage a
// scanning radio parks wherever its last scan left it, so the sensor's
// triggers stop arriving. We remember the AP channel and re-pin the radio to
// it after every failed reconnect attempt (channel 1 before the first
// successful connect).
uint8_t lastKnownWifiChannel = 0;
bool currentOccupancyActive = false;
bool currentCycleCaptureAttempted = false;
bool currentCycleCaptureSucceeded = false;
bool currentCycleCaptureInProgress = false;
uint32_t currentCycleSequence = 0;
uint32_t pendingCaptureSequence = 0;
bool pendingEspNowCapture = false;
uint8_t currentSensorPeerMac[6] = {0, 0, 0, 0, 0, 0};

// Photo captured for the current occupancy cycle, copied out of the camera
// driver's buffer so it survives WiFi outages: the SAME frame taken at the
// moment the car arrived is re-sent after reconnection instead of
// re-photographing whatever the camera sees later. Freed once the backend
// answers (success or rejection) or when the spot becomes free again.
uint8_t *pendingPhotoBuffer = nullptr;
size_t pendingPhotoLength = 0;

portMUX_TYPE espNowMessageMux = portMUX_INITIALIZER_UNLOCKED;
EspNowSensorStateMessage pendingSensorStateMessage = {};
uint8_t pendingSensorSourceMac[6] = {0, 0, 0, 0, 0, 0};
volatile bool hasPendingSensorStateMessage = false;

}  // namespace

void printStatus(const String &line1, const String &line2 = "") {
  Serial.print("[STATUS] ");
  Serial.print(line1);
  if (line2.length() > 0) {
    Serial.print(" | ");
    Serial.print(line2);
  }
  Serial.println();
}

void showStatus(const String &line1, const String &line2) {
  printStatus(line1, line2);
}

void pulseGateRelay() {
  if (PARKME_GATE_RELAY_PIN < 0) {
    return;
  }

  digitalWrite(PARKME_GATE_RELAY_PIN, HIGH);
  delay(PARKME_GATE_RELAY_PULSE_MS);
  digitalWrite(PARKME_GATE_RELAY_PIN, LOW);
}

bool ensureEspNowPeer(const uint8_t peerMac[6]) {
  if (!espNowReady) {
    return false;
  }

  if (esp_now_is_peer_exist(peerMac)) {
    return true;
  }

  esp_now_peer_info_t peerInfo = {};
  memcpy(peerInfo.peer_addr, peerMac, sizeof(peerInfo.peer_addr));
  peerInfo.channel = 0;
  peerInfo.encrypt = false;
  return esp_now_add_peer(&peerInfo) == ESP_OK;
}

void sendEspNowAck(const uint8_t targetMac[6],
                   uint32_t sequence,
                   uint8_t status,
                   const String &detail) {
  if (!ensureEspNowPeer(targetMac)) {
    Serial.println("ESP-NOW ack skipped because the sensor peer is unavailable.");
    return;
  }

  EspNowCameraAckMessage message = {};
  message.magic = PARKME_ESPNOW_PROTOCOL_MAGIC;
  message.version = PARKME_ESPNOW_PROTOCOL_VERSION;
  message.messageType = ESPNOW_MESSAGE_CAMERA_ACK;
  message.sequence = sequence;
  message.status = status;
  copyStringToFixedBuffer(WiFi.macAddress(),
                          message.senderMac,
                          sizeof(message.senderMac));
  copyStringToFixedBuffer(detail, message.detail, sizeof(message.detail));

  esp_err_t sendStatus =
      esp_now_send(targetMac, reinterpret_cast<const uint8_t *>(&message),
                   sizeof(message));
  if (sendStatus != ESP_OK) {
    Serial.print("ESP-NOW ack failed with status ");
    Serial.println(static_cast<int>(sendStatus));
  }
}

void handleEspNowSensorStateReceived(const uint8_t *macAddress,
                                     const uint8_t *data,
                                     int dataLength) {
  if (dataLength != static_cast<int>(sizeof(EspNowSensorStateMessage))) {
    return;
  }

  EspNowSensorStateMessage message = {};
  memcpy(&message, data, sizeof(message));
  if (!isEspNowMessageEnvelopeValid(message, ESPNOW_MESSAGE_SENSOR_STATE)) {
    return;
  }

  portENTER_CRITICAL(&espNowMessageMux);
  pendingSensorStateMessage = message;
  memcpy(pendingSensorSourceMac, macAddress, sizeof(pendingSensorSourceMac));
  hasPendingSensorStateMessage = true;
  portEXIT_CRITICAL(&espNowMessageMux);
}

bool takePendingSensorStateMessage(EspNowSensorStateMessage &message,
                                   uint8_t sourceMac[6]) {
  bool hasMessage = false;
  portENTER_CRITICAL(&espNowMessageMux);
  if (hasPendingSensorStateMessage) {
    message = pendingSensorStateMessage;
    memcpy(sourceMac, pendingSensorSourceMac, 6);
    hasPendingSensorStateMessage = false;
    hasMessage = true;
  }
  portEXIT_CRITICAL(&espNowMessageMux);
  return hasMessage;
}

bool initEspNow() {
  if (esp_now_init() != ESP_OK) {
    Serial.println("ESP-NOW init failed on camera node.");
    return false;
  }

  esp_now_register_recv_cb(handleEspNowSensorStateReceived);
  Serial.println("ESP-NOW ready on camera node.");
  return true;
}

void freePendingPhoto(const char *reason) {
  if (pendingPhotoBuffer == nullptr) {
    return;
  }
  free(pendingPhotoBuffer);
  pendingPhotoBuffer = nullptr;
  pendingPhotoLength = 0;
  Serial.print("Pending photo discarded: ");
  Serial.println(reason);
}

void resetOccupancyCycle(const char *reason) {
  // A stale photo must never be sent for a car that already left.
  freePendingPhoto(reason);
  currentOccupancyActive = false;
  currentCycleCaptureAttempted = false;
  currentCycleCaptureSucceeded = false;
  currentCycleCaptureInProgress = false;
  pendingEspNowCapture = false;
  pendingCaptureSequence = 0;
  currentCycleSequence = 0;
  memset(currentSensorPeerMac, 0, sizeof(currentSensorPeerMac));

  Serial.print("Occupancy cycle reset: ");
  Serial.println(reason);
}

void processSensorStateMessage(const EspNowSensorStateMessage &message,
                               const uint8_t sourceMac[6]) {
  String spotId = String(message.spotId);
  SpotState state = static_cast<SpotState>(message.state);

  // Simplified: Accept ESP-NOW trigger from any sensor without spotId matching

  Serial.print("ESP-NOW state for ");
  Serial.print(spotId);
  Serial.print(": ");
  Serial.print(state == STATE_OCCUPIED ? "OCCUPIED" : "FREE");
  Serial.print(" seq=");
  Serial.println(message.sequence);

  if (state == STATE_FREE) {
    sendEspNowAck(sourceMac,
                  message.sequence,
                  ESPNOW_CAMERA_ACK_SPOT_FREED,
                  "spot_freed");
    resetOccupancyCycle("spot_freed");
    showStatus("Spot free", "Waiting car");
    return;
  }

  if (state != STATE_OCCUPIED) {
    return;
  }

  // The sensor bumps the sequence on every state transition, and the ESP-NOW
  // mailbox holds only the newest unprocessed message — so a FREE that arrived
  // while loop() was busy (uploading, showing a verdict) can be overwritten by
  // the next OCCUPIED and never seen. An OCCUPIED whose sequence differs from
  // the cycle we latched therefore means a NEW car: clear the per-cycle
  // capture latch and any stale photo so this arrival gets photographed too.
  if (currentCycleSequence != 0 && message.sequence != currentCycleSequence) {
    resetOccupancyCycle("new occupancy cycle (missed FREE)");
  }

  currentOccupancyActive = true;
  currentCycleSequence = message.sequence;
  memcpy(currentSensorPeerMac, sourceMac, sizeof(currentSensorPeerMac));

  if (!currentCycleCaptureAttempted && !pendingEspNowCapture) {
    pendingEspNowCapture = true;
    pendingCaptureSequence = message.sequence;
    sendEspNowAck(sourceMac,
                  message.sequence,
                  ESPNOW_CAMERA_ACK_RECEIVED,
                  "capture_queued");
  }
}

bool connectWiFi() {
  lastWifiAttemptAtMs = millis();

  showStatus("Connecting WiFi", "Please wait...");
  WiFi.begin(PARKME_WIFI_SSID, PARKME_WIFI_PASSWORD);

  unsigned long startedAtMs = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - startedAtMs < 12000) {
    delay(400);
  }

  if (WiFi.status() == WL_CONNECTED) {
    lastKnownWifiChannel = WiFi.channel();
    showStatus("WiFi connected", "Ready to scan");
    Serial.print("WiFi connected. IP: ");
    Serial.print(WiFi.localIP());
    Serial.print(" channel: ");
    Serial.println(lastKnownWifiChannel);
    Serial.print("MAC: ");
    Serial.println(WiFi.macAddress());
    return true;
  }

  // Stop the pending association attempt, then park the radio back on the
  // AP's channel so ESP-NOW triggers from the sensor keep arriving while we
  // wait for the next retry.
  WiFi.disconnect();
  uint8_t pinChannel = lastKnownWifiChannel > 0 ? lastKnownWifiChannel : 1;
  esp_wifi_set_channel(pinChannel, WIFI_SECOND_CHAN_NONE);
  showStatus("WiFi failed", "Retry later");
  Serial.print("WiFi connection failed. Radio pinned to channel ");
  Serial.println(pinChannel);
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
    showStatus("Camera failed", "Check wiring");
    return false;
  }

  return true;
}

bool sendJsonRequest(const char *path,
                     const String &payload,
                     String &responseBody,
                     int &httpStatusCode) {
  WiFiClient plainClient;
  WiFiClientSecure secureClient;
  Client *client =
      String(PARKME_SERVER_SCHEME) == "https" ? &secureClient : &plainClient;
  secureClient.setInsecure();
  client->setTimeout(PARKME_GATE_HTTP_TIMEOUT_MS);

  if (!client->connect(PARKME_SERVER_HOST, PARKME_SERVER_PORT)) {
    Serial.println("Cannot connect to backend.");
    return false;
  }

  client->print(String("POST ") + path + " HTTP/1.1\r\n");
  client->print(String("Host: ") + PARKME_SERVER_HOST + "\r\n");
  client->print("Connection: close\r\n");
  client->print("Content-Type: application/json\r\n");
  client->print("Content-Length: " + String(payload.length()) + "\r\n\r\n");
  client->print(payload);

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
    if (headerLine == "\r" || headerLine.length() == 0) {
      break;
    }
  }

  responseBody = client->readString();
  client->stop();
  return true;
}


bool capturePendingPhoto() {
  if (pendingPhotoBuffer != nullptr) {
    // A photo from earlier in this occupancy cycle is still waiting to be
    // sent (WiFi outage); reuse it instead of photographing again.
    Serial.println("Reusing photo captured earlier this cycle.");
    return true;
  }

  camera_fb_t *frame = nullptr;

  Serial.println("Capture requested. Taking photo...");

  if (PARKME_GATE_FLASH_LED_PIN >= 0) {
    digitalWrite(PARKME_GATE_FLASH_LED_PIN, HIGH);
    // Wait for the flash to illuminate and auto-exposure to adjust
    delay(80);
  }

  // Dummy grab to flush the stale frame from the camera's FIFO buffer
  frame = esp_camera_fb_get();
  if (frame) {
    esp_camera_fb_return(frame);
  }

  // Second dummy grab (required because config.fb_count can be 2)
  frame = esp_camera_fb_get();
  if (frame) {
    esp_camera_fb_return(frame);
  }

  // Grab the fresh frame
  frame = esp_camera_fb_get();

  if (PARKME_GATE_FLASH_LED_PIN >= 0) {
    digitalWrite(PARKME_GATE_FLASH_LED_PIN, LOW);
  }

  if (!frame) {
    Serial.println("Camera capture failed.");
    return false;
  }

  // Copy the JPEG out of the driver's buffer (PSRAM when available) so the
  // driver buffer can be released immediately and the photo survives until
  // the backend has actually received it.
  uint8_t *copyBuffer = static_cast<uint8_t *>(
      psramFound() ? ps_malloc(frame->len) : malloc(frame->len));
  if (copyBuffer == nullptr) {
    Serial.println("Not enough memory to hold the photo. Will retry on next ping.");
    esp_camera_fb_return(frame);
    return false;
  }

  memcpy(copyBuffer, frame->buf, frame->len);
  pendingPhotoLength = frame->len;
  pendingPhotoBuffer = copyBuffer;
  esp_camera_fb_return(frame);

  Serial.print("Photo captured successfully. Size: ");
  Serial.print(pendingPhotoLength);
  Serial.println(" bytes");
  return true;
}

bool uploadPendingPhoto(String &responseBody, int &httpStatusCode) {
  if (pendingPhotoBuffer == nullptr) {
    Serial.println("No pending photo to upload.");
    return false;
  }

  const String boundary = "----ParkMeBoundary7MA4YWxkTrZu0gW";
  String part1 = "--" + boundary + "\r\nContent-Disposition: form-data; name=\"camera_mac\"\r\n\r\n" + WiFi.macAddress() + "\r\n";
  String part2 = "--" + boundary + "\r\nContent-Disposition: form-data; name=\"file\"; filename=\"capture.jpg\"\r\nContent-Type: image/jpeg\r\n\r\n";
  String closing = "\r\n--" + boundary + "--\r\n";

  size_t contentLength = part1.length() + part2.length() + pendingPhotoLength + closing.length();

  WiFiClient plainClient;
  WiFiClientSecure secureClient;
  if (String(PARKME_SERVER_SCHEME) == "https") secureClient.setInsecure();

  int maxRetries = 3;
  bool success = false;

  for (int attempt = 1; attempt <= maxRetries; attempt++) {
    Serial.print("Uploading photo to backend (Attempt ");
    Serial.print(attempt);
    Serial.println(")...");

    Client *client = String(PARKME_SERVER_SCHEME) == "https" ? static_cast<Client*>(&secureClient) : static_cast<Client*>(&plainClient);
    client->setTimeout(PARKME_GATE_HTTP_TIMEOUT_MS);

    if (!client->connect(PARKME_SERVER_HOST, PARKME_SERVER_PORT)) {
      Serial.println("Cannot connect to backend.");
      delay(1000);
      continue;
    }

    client->print(String("POST ") + PARKME_API_GATE_ENTRY_PATH + " HTTP/1.1\r\n");
    client->print(String("Host: ") + PARKME_SERVER_HOST + "\r\n");
    client->print("Connection: close\r\n");
    client->print("Content-Type: multipart/form-data; boundary=" + boundary + "\r\n");
    client->print("Content-Length: " + String(contentLength) + "\r\n\r\n");
    client->print(part1);
    client->print(part2);

    // WiFiClientSecure::write() sends at most one TLS record (~16 KB) per call
    // and returns the bytes actually written, so a single write of the whole
    // JPEG silently truncates the body over HTTPS. Send in checked chunks.
    size_t bytesSent = 0;
    while (bytesSent < pendingPhotoLength) {
      size_t chunkSize = pendingPhotoLength - bytesSent;
      // One full TLS record per write; the loop already handles short writes,
      // so if the stack caps a write lower we just continue from there.
      if (chunkSize > 16384) chunkSize = 16384;
      size_t written = client->write(pendingPhotoBuffer + bytesSent, chunkSize);
      if (written == 0) {
        break;
      }
      bytesSent += written;
    }
    if (bytesSent < pendingPhotoLength) {
      client->stop();
      Serial.printf("Body write failed at %u/%u bytes.\n",
                    (unsigned)bytesSent, (unsigned)pendingPhotoLength);
      delay(1000);
      continue;
    }
    client->print(closing);

    unsigned long waitStartedAtMs = millis();
    while (!client->available() && client->connected() && millis() - waitStartedAtMs < PARKME_GATE_HTTP_TIMEOUT_MS) {
      delay(10);
    }

    if (!client->available()) {
      client->stop();
      Serial.println("Backend response timeout.");
      delay(1000);
      continue;
    }

    String statusLine = client->readStringUntil('\n');
    httpStatusCode = parseHttpStatusCode(statusLine);

    while (client->connected()) {
      String headerLine = client->readStringUntil('\n');
      if (headerLine == "\r" || headerLine.length() == 0) {
        break;
      }
    }

    responseBody = client->readString();
    client->stop();
    success = true;
    break; // Upload succeeded, exit retry loop!
  }

  if (!success) {
    // No HTTP response at all (connect failure / timeout): keep the photo so
    // the exact same frame is re-sent once WiFi comes back.
    Serial.println("All upload attempts failed. Photo kept for retry after reconnect.");
    return false;
  }

  // The backend answered, so connectivity was fine; whether it accepted or
  // rejected the photo, re-sending the same bytes adds nothing.
  freePendingPhoto(httpStatusCode >= 200 && httpStatusCode < 300
                       ? "upload complete"
                       : "server rejected photo");

  Serial.print("HTTP ");
  Serial.print(httpStatusCode);
  Serial.print(" | ");
  Serial.println(responseBody);

  return true;
}

GateAction handleServerDecision(const String &responseBody) {
  GateAction action = parseGateAction(responseBody);
  String message = extractGateMessage(responseBody);

  switch (action) {
    case ACTION_WELCOME:
      showStatus("Access granted", message);
      pulseGateRelay();
      // No display on this board (status goes to serial; the driver-facing
      // screen is the sensor's OLED, driven by the server). Blocking here
      // only delays processing of the next ESP-NOW message.
      break;
    case ACTION_DENIED:
      showStatus("Access denied", message);
      break;
    case ACTION_RETRY:
      showStatus("Scan again", message);
      delay(PARKME_GATE_RETRY_STATUS_MS);
      break;
    default:
      showStatus("Server error", "Unexpected data");
      delay(PARKME_GATE_RETRY_STATUS_MS);
      break;
  }

  return action;
}

GateAction performGateScan() {
  // Photograph the car at the moment of arrival even if WiFi is down; the
  // persisted frame is re-sent unchanged once connectivity returns.
  showStatus("Capturing...", "Hold still");
  if (!capturePendingPhoto()) {
    Serial.println("Capture failed.");
    showStatus("Capture failed", "Check camera");
    return ACTION_UNKNOWN;
  }

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi offline after capture. Attempting reconnect...");
    showStatus("WiFi offline", "Reconnecting");
    connectWiFi();
  }

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi still offline. Photo saved; will send after reconnect.");
    showStatus("WiFi offline", "Photo saved");
    return ACTION_UNKNOWN;
  }

  String responseBody;
  int httpStatusCode = -1;

  if (!uploadPendingPhoto(responseBody, httpStatusCode)) {
    Serial.println("Upload failed. Photo saved; will retry on next ping.");
    showStatus("Upload failed", "Retry next ping");
    return ACTION_UNKNOWN;
  }

  if (httpStatusCode < 200 || httpStatusCode >= 300) {
    Serial.println("Backend rejected the captured photo.");
    showStatus("Server rejected", "Check backend");
    return ACTION_UNKNOWN;
  }

  return handleServerDecision(responseBody);
}

void handlePendingEspNowCapture() {
  if (!pendingEspNowCapture) {
    return;
  }

  pendingEspNowCapture = false;
  currentCycleCaptureAttempted = true;
  currentCycleCaptureInProgress = true;
  sendEspNowAck(currentSensorPeerMac,
                pendingCaptureSequence,
                ESPNOW_CAMERA_ACK_CAPTURE_STARTED,
                "capture_started");

  GateAction result = performGateScan();

  currentCycleCaptureInProgress = false;
  if (result == ACTION_WELCOME || result == ACTION_DENIED) {
    currentCycleCaptureSucceeded = true;
    sendEspNowAck(currentSensorPeerMac,
                  pendingCaptureSequence,
                  ESPNOW_CAMERA_ACK_CAPTURE_COMPLETED,
                  "capture_completed");
    showStatus("Ready for sensor", "Waiting car");
  } else {
    // Do not deadlock the cycle after an upload failure. The sensor re-broadcasts
    // OCCUPIED every few seconds, so clearing this latch allows an automatic retry
    // on the next sync instead of waiting forever for a FREE transition.
    currentCycleCaptureAttempted = false;
    sendEspNowAck(currentSensorPeerMac,
                  pendingCaptureSequence,
                  ESPNOW_CAMERA_ACK_CAPTURE_FAILED,
                  "capture_failed");
    showStatus("Capture failed", "Retry next ping");
  }
}

void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println();
  Serial.println("ParkMe Camera Node Started");
  Serial.println("Boot stage: pin setup");

  if (PARKME_GATE_FLASH_LED_PIN >= 0) {
    pinMode(PARKME_GATE_FLASH_LED_PIN, OUTPUT);
    digitalWrite(PARKME_GATE_FLASH_LED_PIN, LOW);
  }

  if (PARKME_GATE_RELAY_PIN >= 0) {
    pinMode(PARKME_GATE_RELAY_PIN, OUTPUT);
    digitalWrite(PARKME_GATE_RELAY_PIN, LOW);
  }

  Serial.println("Boot stage: camera init");
  if (!initCamera()) {
    return;
  }

  Serial.println("Boot stage: WiFi init");
  WiFi.mode(WIFI_STA);
  // Manual reconnect only: the SDK's background auto-reconnect keeps
  // scanning channels, which un-pins the radio and breaks ESP-NOW reception
  // during outages. maintainWiFi() retries on our schedule instead.
  WiFi.setAutoReconnect(false);
  espNowReady = initEspNow();
  connectWiFi();
  Serial.print("Gate spot: ");
  Serial.println(PARKME_GATE_SPOT_ID);
  Serial.print("Backend: ");
  Serial.print(PARKME_SERVER_SCHEME);
  Serial.print("://");
  Serial.print(PARKME_SERVER_HOST);
  Serial.print(":");
  Serial.println(PARKME_SERVER_PORT);
  showStatus("Ready for ESP-NOW", "Waiting sensor");
}

void loop() {
  maintainWiFi();

  EspNowSensorStateMessage sensorMessage = {};
  uint8_t sourceMac[6] = {0, 0, 0, 0, 0, 0};
  if (takePendingSensorStateMessage(sensorMessage, sourceMac)) {
    processSensorStateMessage(sensorMessage, sourceMac);
  }

  handlePendingEspNowCapture();
  delay(50);
}

