#include <HTTPClient.h>
#include <Preferences.h>
#include <esp_now.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <Wire.h>

#include "ParkMeCommon.h"
#include "ParkMeConfig.h"

using namespace parkme;

namespace {

Preferences preferences;

struct PendingTelemetry {
  uint8_t status;
  uint8_t batteryPercent;
  uint8_t valid;
};

PendingTelemetry pendingTelemetry = {0, 100, 0};

float baselineDistanceCm = PARKME_SENSOR_DEFAULT_BASELINE_CM;
float occupiedThresholdCm = PARKME_SENSOR_OCCUPIED_THRESHOLD_CM;

SpotState lastPublishedState = STATE_UNKNOWN;
unsigned long lastSampleAtMs = 0;
unsigned long lastSuccessfulPublishAtMs = 0;
unsigned long lastWifiAttemptAtMs = 0;
unsigned long calibrationButtonPressedAtMs = 0;
unsigned long lastDisplayPollAtMs = 0;
unsigned long activeMessageUntilAtMs = 0;
unsigned long localCameraMessageUntilAtMs = 0;
unsigned long lastEspNowStateSentAtMs = 0;

float lastMeasuredDistanceCm = -1.0f;
SpotState lastMeasuredState = STATE_UNKNOWN;
int lastMeasuredBatteryPercent = 100;
SpotState lastEspNowState = STATE_UNKNOWN;
uint32_t lastEspNowSequence = 0;

String currentScreenTitle = "ParkMe";
String currentScreenMessage = "Booting";
String lastRenderedSignature;
String lastEspNowAckDetail;
String localCameraScreenTitle;
String localCameraScreenMessage;

bool graphicsReady = false;
bool espNowReady = false;
uint8_t selectedDisplayAddress = 0;
portMUX_TYPE espNowAckMux = portMUX_INITIALIZER_UNLOCKED;
volatile bool hasPendingEspNowAck = false;
volatile uint8_t pendingEspNowAckStatus = 0;
char pendingEspNowAckDetail[24] = {0};
const uint8_t kEspNowBroadcastPeer[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};

bool addEspNowPeerIfNeeded(const uint8_t peerMac[6]) {
  if (esp_now_is_peer_exist(peerMac)) {
    return true;
  }

  esp_now_peer_info_t peerInfo = {};
  memcpy(peerInfo.peer_addr, peerMac, sizeof(peerInfo.peer_addr));
  peerInfo.channel = 0;
  peerInfo.encrypt = false;
  return esp_now_add_peer(&peerInfo) == ESP_OK;
}

constexpr uint8_t kDisplayWidth = 128;
constexpr uint8_t kDisplayHeight = 64;
constexpr uint8_t kDisplayPages = kDisplayHeight / 8;
constexpr unsigned long kSensorEchoTimeoutUs = 30000;
constexpr float kSensorMeasurementCapCm =
    (kSensorEchoTimeoutUs * 0.0343f) / 2.0f;
uint8_t displayBuffer[kDisplayWidth * kDisplayPages] = {0};

const uint8_t FONT_SPACE[5] = {0x00, 0x00, 0x00, 0x00, 0x00};
const uint8_t FONT_0[5] = {0x3E, 0x45, 0x49, 0x51, 0x3E};
const uint8_t FONT_1[5] = {0x00, 0x21, 0x7F, 0x01, 0x00};
const uint8_t FONT_2[5] = {0x21, 0x43, 0x45, 0x49, 0x31};
const uint8_t FONT_3[5] = {0x42, 0x41, 0x51, 0x69, 0x46};
const uint8_t FONT_4[5] = {0x0C, 0x14, 0x24, 0x7F, 0x04};
const uint8_t FONT_5[5] = {0x72, 0x51, 0x51, 0x51, 0x4E};
const uint8_t FONT_6[5] = {0x1E, 0x29, 0x49, 0x49, 0x06};
const uint8_t FONT_7[5] = {0x40, 0x47, 0x48, 0x50, 0x60};
const uint8_t FONT_8[5] = {0x36, 0x49, 0x49, 0x49, 0x36};
const uint8_t FONT_9[5] = {0x30, 0x49, 0x49, 0x4A, 0x3C};
const uint8_t FONT_A[5] = {0x7E, 0x11, 0x11, 0x11, 0x7E};
const uint8_t FONT_B[5] = {0x7F, 0x49, 0x49, 0x49, 0x36};
const uint8_t FONT_C[5] = {0x3E, 0x41, 0x41, 0x41, 0x22};
const uint8_t FONT_D[5] = {0x7F, 0x41, 0x41, 0x22, 0x1C};
const uint8_t FONT_E[5] = {0x7F, 0x49, 0x49, 0x49, 0x41};
const uint8_t FONT_F[5] = {0x7F, 0x09, 0x09, 0x09, 0x01};
const uint8_t FONT_G[5] = {0x3E, 0x41, 0x49, 0x49, 0x7A};
const uint8_t FONT_H[5] = {0x7F, 0x08, 0x08, 0x08, 0x7F};
const uint8_t FONT_I[5] = {0x00, 0x41, 0x7F, 0x41, 0x00};
const uint8_t FONT_J[5] = {0x20, 0x40, 0x41, 0x3F, 0x01};
const uint8_t FONT_K[5] = {0x7F, 0x08, 0x14, 0x22, 0x41};
const uint8_t FONT_L[5] = {0x7F, 0x40, 0x40, 0x40, 0x40};
const uint8_t FONT_M[5] = {0x7F, 0x02, 0x0C, 0x02, 0x7F};
const uint8_t FONT_N[5] = {0x7F, 0x04, 0x08, 0x10, 0x7F};
const uint8_t FONT_O[5] = {0x3E, 0x41, 0x41, 0x41, 0x3E};
const uint8_t FONT_P[5] = {0x7F, 0x09, 0x09, 0x09, 0x06};
const uint8_t FONT_Q[5] = {0x3E, 0x41, 0x51, 0x21, 0x5E};
const uint8_t FONT_R[5] = {0x7F, 0x09, 0x19, 0x29, 0x46};
const uint8_t FONT_S[5] = {0x46, 0x49, 0x49, 0x49, 0x31};
const uint8_t FONT_T[5] = {0x01, 0x01, 0x7F, 0x01, 0x01};
const uint8_t FONT_U[5] = {0x3F, 0x40, 0x40, 0x40, 0x3F};
const uint8_t FONT_V[5] = {0x1F, 0x20, 0x40, 0x20, 0x1F};
const uint8_t FONT_W[5] = {0x7F, 0x20, 0x18, 0x20, 0x7F};
const uint8_t FONT_X[5] = {0x63, 0x14, 0x08, 0x14, 0x63};
const uint8_t FONT_Y[5] = {0x03, 0x04, 0x78, 0x04, 0x03};
const uint8_t FONT_Z[5] = {0x61, 0x51, 0x49, 0x45, 0x43};

}  // namespace

void handleEspNowSend(const uint8_t *macAddress, esp_now_send_status_t status) {
  Serial.print("ESP-NOW send to ");
  Serial.print(formatMacAddress(macAddress));
  Serial.print(": ");
  Serial.println(status == ESP_NOW_SEND_SUCCESS ? "ok" : "failed");
}

void handleEspNowReceive(const uint8_t *macAddress,
                         const uint8_t *data,
                         int dataLength) {
  if (dataLength != static_cast<int>(sizeof(EspNowCameraAckMessage))) {
    return;
  }

  EspNowCameraAckMessage message = {};
  memcpy(&message, data, sizeof(message));
  if (!isEspNowMessageEnvelopeValid(message, ESPNOW_MESSAGE_CAMERA_ACK)) {
    return;
  }

  lastEspNowAckDetail = String(message.detail);
  Serial.print("ESP-NOW ack from ");
  Serial.print(formatMacAddress(macAddress));
  Serial.print(" seq=");
  Serial.print(message.sequence);
  Serial.print(" status=");
  Serial.print(message.status);
  if (lastEspNowAckDetail.length() > 0) {
    Serial.print(" detail=");
    Serial.print(lastEspNowAckDetail);
  }
  Serial.println();

  portENTER_CRITICAL(&espNowAckMux);
  pendingEspNowAckStatus = message.status;
  memcpy(pendingEspNowAckDetail, message.detail, sizeof(pendingEspNowAckDetail));
  hasPendingEspNowAck = true;
  portEXIT_CRITICAL(&espNowAckMux);
}

bool initEspNow() {
  uint8_t peerMac[6];
  bool hasConfiguredCameraPeer =
      parseMacAddress(PARKME_CAMERA_ESPNOW_PEER_MAC, peerMac);

  if (esp_now_init() != ESP_OK) {
    Serial.println("ESP-NOW init failed on sensor node.");
    return false;
  }

  esp_now_register_send_cb(handleEspNowSend);
  esp_now_register_recv_cb(handleEspNowReceive);

  if (!addEspNowPeerIfNeeded(kEspNowBroadcastPeer)) {
    Serial.println("ESP-NOW could not add the broadcast peer.");
    return false;
  }

  if (hasConfiguredCameraPeer && !addEspNowPeerIfNeeded(peerMac)) {
    Serial.println("ESP-NOW could not add the configured camera peer.");
    return false;
  }

  if (hasConfiguredCameraPeer) {
    Serial.print("ESP-NOW ready. Camera peer: ");
    Serial.println(PARKME_CAMERA_ESPNOW_PEER_MAC);
    Serial.println("ESP-NOW broadcast fallback is also enabled.");
  } else {
    Serial.println("ESP-NOW ready. Using broadcast trigger because the camera peer MAC is empty or invalid.");
  }
  return true;
}

bool takePendingEspNowAck(uint8_t &status, char detailBuffer[24]) {
  bool hasAck = false;
  portENTER_CRITICAL(&espNowAckMux);
  if (hasPendingEspNowAck) {
    status = pendingEspNowAckStatus;
    memcpy(detailBuffer, pendingEspNowAckDetail, 24);
    hasPendingEspNowAck = false;
    hasAck = true;
  }
  portEXIT_CRITICAL(&espNowAckMux);
  return hasAck;
}

bool isTimedMessageActive(unsigned long expiresAtMs) {
  return expiresAtMs > 0 && static_cast<long>(millis() - expiresAtMs) < 0;
}

bool isServerMessageActive() {
  return isTimedMessageActive(activeMessageUntilAtMs);
}

bool isLocalCameraMessageActive() {
  return isTimedMessageActive(localCameraMessageUntilAtMs);
}

bool shouldSendEspNowState(SpotState state, unsigned long nowMs) {
  if (!espNowReady || !isKnownState(state)) {
    return false;
  }

  if (!isKnownState(lastEspNowState) || state != lastEspNowState) {
    return true;
  }

  return nowMs - lastEspNowStateSentAtMs >=
         PARKME_SENSOR_ESPNOW_STATE_SYNC_INTERVAL_MS;
}

void sendEspNowState(SpotState state, int batteryPercent) {
  if (!espNowReady) {
    return;
  }

  unsigned long nowMs = millis();
  if (!shouldSendEspNowState(state, nowMs)) {
    return;
  }

  if (!isKnownState(lastEspNowState) || state != lastEspNowState) {
    lastEspNowSequence++;
    lastEspNowState = state;
  }

  EspNowSensorStateMessage message = {};
  message.magic = PARKME_ESPNOW_PROTOCOL_MAGIC;
  message.version = PARKME_ESPNOW_PROTOCOL_VERSION;
  message.messageType = ESPNOW_MESSAGE_SENSOR_STATE;
  message.sequence = lastEspNowSequence;
  message.state = static_cast<uint8_t>(state);
  message.batteryPercent =
      static_cast<uint8_t>(clampValue(batteryPercent, 0, 100));
  copyStringToFixedBuffer(String(PARKME_GATE_SPOT_ID),
                          message.spotId,
                          sizeof(message.spotId));
  copyStringToFixedBuffer(WiFi.macAddress(),
                          message.senderMac,
                          sizeof(message.senderMac));

  bool sentSuccessfully = false;
  bool directQueued = false;
  bool broadcastQueued = false;

  uint8_t peerMac[6];
  if (parseMacAddress(PARKME_CAMERA_ESPNOW_PEER_MAC, peerMac)) {
    esp_err_t directStatus =
        esp_now_send(peerMac, reinterpret_cast<const uint8_t *>(&message),
                     sizeof(message));
    if (directStatus == ESP_OK) {
      sentSuccessfully = true;
      directQueued = true;
    } else {
      Serial.print("ESP-NOW direct send failed with status ");
      Serial.println(static_cast<int>(directStatus));
    }
  }

  esp_err_t broadcastStatus =
      esp_now_send(kEspNowBroadcastPeer,
                   reinterpret_cast<const uint8_t *>(&message),
                   sizeof(message));
  if (broadcastStatus == ESP_OK) {
    sentSuccessfully = true;
    broadcastQueued = true;
  } else {
    Serial.print("ESP-NOW broadcast send failed with status ");
    Serial.println(static_cast<int>(broadcastStatus));
  }

  if (sentSuccessfully) {
    lastEspNowStateSentAtMs = nowMs;
    Serial.print("ESP-NOW state queued seq=");
    Serial.print(message.sequence);
    Serial.print(" state=");
    Serial.print(state == STATE_OCCUPIED ? "OCCUPIED" : "FREE");
    Serial.print(" direct=");
    Serial.print(directQueued ? "yes" : "no");
    Serial.print(" broadcast=");
    Serial.println(broadcastQueued ? "yes" : "no");
  }
}

const uint8_t *fontFor(char c) {
  switch (c) {
    case '0': return FONT_0;
    case '1': return FONT_1;
    case '2': return FONT_2;
    case '3': return FONT_3;
    case '4': return FONT_4;
    case '5': return FONT_5;
    case '6': return FONT_6;
    case '7': return FONT_7;
    case '8': return FONT_8;
    case '9': return FONT_9;
    case 'A': return FONT_A;
    case 'B': return FONT_B;
    case 'C': return FONT_C;
    case 'D': return FONT_D;
    case 'E': return FONT_E;
    case 'F': return FONT_F;
    case 'G': return FONT_G;
    case 'H': return FONT_H;
    case 'I': return FONT_I;
    case 'J': return FONT_J;
    case 'K': return FONT_K;
    case 'L': return FONT_L;
    case 'M': return FONT_M;
    case 'N': return FONT_N;
    case 'O': return FONT_O;
    case 'P': return FONT_P;
    case 'Q': return FONT_Q;
    case 'R': return FONT_R;
    case 'S': return FONT_S;
    case 'T': return FONT_T;
    case 'U': return FONT_U;
    case 'V': return FONT_V;
    case 'W': return FONT_W;
    case 'X': return FONT_X;
    case 'Y': return FONT_Y;
    case 'Z': return FONT_Z;
    default: return FONT_SPACE;
  }
}

String normalizeDisplayText(String text) {
  text.replace("\n", " ");
  text.toUpperCase();

  for (size_t i = 0; i < text.length(); ++i) {
    char c = text[i];
    bool allowed = (c >= 'A' && c <= 'Z') ||
                   (c >= '0' && c <= '9') ||
                   c == ' ';
    if (!allowed) {
      text.setCharAt(i, ' ');
    }
  }

  return text;
}

void oledCommand(uint8_t command) {
  Wire.beginTransmission(selectedDisplayAddress);
  Wire.write(0x00);
  Wire.write(command);
  Wire.endTransmission();
}

void oledData(const uint8_t *data, uint8_t length) {
  Wire.beginTransmission(selectedDisplayAddress);
  Wire.write(0x40);
  for (uint8_t i = 0; i < length; ++i) {
    Wire.write(data[i]);
  }
  Wire.endTransmission();
}

bool oledAddressResponds(uint8_t address) {
  Wire.beginTransmission(address);
  return Wire.endTransmission() == 0;
}

void oledInit() {
  oledCommand(0xAE);
  oledCommand(0xD5);
  oledCommand(0x80);
  oledCommand(0xA8);
  oledCommand(0x3F);
  oledCommand(0xD3);
  oledCommand(0x00);
  oledCommand(0x40);
  oledCommand(0x8D);
  oledCommand(0x14);
  oledCommand(0xA1);
  oledCommand(0xC8);
  oledCommand(0xDA);
  oledCommand(0x12);
  oledCommand(0x81);
  oledCommand(0xFF);
  oledCommand(0xD9);
  oledCommand(0xF1);
  oledCommand(0xDB);
  oledCommand(0x40);
  oledCommand(0xA4);
  oledCommand(0xA6);
  oledCommand(0xAF);
}

void oledDisplay() {
  for (uint8_t page = 0; page < kDisplayPages; ++page) {
    uint8_t column = PARKME_DISPLAY_COLUMN_OFFSET;
    oledCommand(0xB0 + page);
    oledCommand(0x00 + (column & 0x0F));
    oledCommand(0x10 + ((column >> 4) & 0x0F));

    const uint8_t *pageData = &displayBuffer[page * kDisplayWidth];
    for (uint8_t x = 0; x < kDisplayWidth; x += 16) {
      oledData(&pageData[x], 16);
    }
  }
}

void clearDisplayBuffer() {
  memset(displayBuffer, 0, sizeof(displayBuffer));
}

void setPixel(uint8_t x, uint8_t y, bool enabled) {
  if (x >= kDisplayWidth || y >= kDisplayHeight) {
    return;
  }

  uint16_t index = x + (y / 8) * kDisplayWidth;
  uint8_t mask = 1 << (y % 8);
  if (enabled) {
    displayBuffer[index] |= mask;
  } else {
    displayBuffer[index] &= ~mask;
  }
}

void drawChar(uint8_t x, uint8_t y, char c, uint8_t scale) {
  const uint8_t *glyph = fontFor(c);
  for (uint8_t col = 0; col < 5; ++col) {
    for (uint8_t row = 0; row < 7; ++row) {
      bool pixelOn = glyph[col] & (1 << row);
      for (uint8_t dx = 0; dx < scale; ++dx) {
        for (uint8_t dy = 0; dy < scale; ++dy) {
          setPixel(x + col * scale + dx, y + row * scale + dy, pixelOn);
        }
      }
    }
  }
}

void drawText(uint8_t x, uint8_t y, const String &text, uint8_t scale) {
  uint8_t cursorX = x;
  for (size_t i = 0; i < text.length(); ++i) {
    drawChar(cursorX, y, text[i], scale);
    cursorX += 6 * scale;
  }
}

void splitMessageIntoLines(const String &message, String &line1, String &line2) {
  constexpr size_t kMaxCharsPerLine = 18;
  String normalized = message;
  normalized.replace("\n", " ");
  normalized.trim();

  if (normalized.length() <= kMaxCharsPerLine) {
    line1 = normalized;
    line2 = "";
    return;
  }

  int splitAt = normalized.lastIndexOf(' ', kMaxCharsPerLine);
  if (splitAt <= 0) {
    splitAt = static_cast<int>(kMaxCharsPerLine);
  }

  line1 = normalized.substring(0, splitAt);
  line1.trim();

  line2 = normalized.substring(splitAt);
  line2.trim();
  if (line2.length() > kMaxCharsPerLine) {
    line2 = line2.substring(0, kMaxCharsPerLine);
    line2.trim();
  }
}

void renderToSerial(const String &title, const String &message) {
  String signature = title + "|" + message;
  if (signature == lastRenderedSignature) {
    return;
  }

  lastRenderedSignature = signature;
  Serial.println();
  Serial.println("=== Screen Update ===");
  Serial.println(title);
  if (message.length() > 0) {
    Serial.println(message);
  }
  Serial.println("=====================");
}

void renderToGraphics(const String &title, const String &message) {
  if (!graphicsReady) {
    return;
  }

  String normalizedTitle = normalizeDisplayText(title);
  String normalizedMessage = normalizeDisplayText(message);
  String line1;
  String line2;
  splitMessageIntoLines(normalizedMessage, line1, line2);
  normalizedTitle = fitForLcd(normalizedTitle, 10);
  line1 = fitForLcd(line1, 16);
  line2 = fitForLcd(line2, 16);

  clearDisplayBuffer();
  drawText(4, 4, normalizedTitle, 2);
  drawText(4, 28, line1, 1);
  drawText(4, 44, line2, 1);
  oledDisplay();
}

void showScreen(const String &title, const String &message) {
  currentScreenTitle = title;
  currentScreenMessage = message;
  renderToSerial(title, message);
  renderToGraphics(title, message);
}

bool beginGraphicsDisplay() {
  if (!PARKME_DISPLAY_ENABLE_GRAPHICS) {
    Serial.println("Graphics display disabled in SECRETS.h. Using serial only.");
    return false;
  }

  Wire.begin(PARKME_DISPLAY_SDA_PIN, PARKME_DISPLAY_SCL_PIN);
  Wire.setClock(100000);

  bool foundConfiguredAddress = false;
  uint8_t firstDetectedAddress = 0;
  Serial.print("Scanning I2C on SDA=");
  Serial.print(PARKME_DISPLAY_SDA_PIN);
  Serial.print(" SCL=");
  Serial.println(PARKME_DISPLAY_SCL_PIN);
  for (uint8_t address = 1; address < 127; ++address) {
    Wire.beginTransmission(address);
    uint8_t error = Wire.endTransmission();
    if (error == 0) {
      Serial.print("I2C device found at 0x");
      if (address < 16) {
        Serial.print('0');
      }
      Serial.println(address, HEX);
      if (firstDetectedAddress == 0) {
        firstDetectedAddress = address;
      }
      if (address == PARKME_DISPLAY_I2C_ADDRESS) {
        foundConfiguredAddress = true;
      }
    }
  }

  Serial.print("Configured display address: 0x");
  if (PARKME_DISPLAY_I2C_ADDRESS < 16) {
    Serial.print('0');
  }
  Serial.println(PARKME_DISPLAY_I2C_ADDRESS, HEX);

  if (!foundConfiguredAddress) {
    Serial.println("Configured display address was not found on the I2C bus.");
  }

  uint8_t selectedAddress = PARKME_DISPLAY_I2C_ADDRESS;
  if (!foundConfiguredAddress && firstDetectedAddress != 0) {
    selectedAddress = firstDetectedAddress;
    Serial.print("Using detected display address instead: 0x");
    if (selectedAddress < 16) {
      Serial.print('0');
    }
    Serial.println(selectedAddress, HEX);
  }

  if (selectedAddress == 0) {
    Serial.println("No I2C display address available.");
    return false;
  }

  if (!oledAddressResponds(selectedAddress)) {
    Serial.println("Selected OLED address did not respond.");
    return false;
  }

  selectedDisplayAddress = selectedAddress;
  Serial.println("Display driver: LOW-LEVEL SSD1306/SH1106 STYLE");
  oledInit();
  clearDisplayBuffer();
  drawText(10, 12, "WELCOME", 2);
  drawText(34, 44, "PARKME", 1);
  oledDisplay();
  delay(500);
  return true;
}

void showLocalSensorScreen() {
  String title = String("Spot ") + PARKME_GATE_SPOT_ID;
  String message;

  if (!isKnownState(lastMeasuredState)) {
    message = "Waiting sensor";
  } else if (lastMeasuredState == STATE_OCCUPIED) {
    message = "Occupied ";
    if (lastMeasuredDistanceCm > 0.0f) {
      message += String(lastMeasuredDistanceCm, 0);
      message += "cm";
    }
  } else {
    message = "Free ";
    if (lastMeasuredDistanceCm > 0.0f) {
      message += String(lastMeasuredDistanceCm, 0);
      message += "cm";
    }
  }

  message += " B";
  message += String(lastMeasuredBatteryPercent);
  message += "%";

  showScreen(title, message);
}

void clearLocalCameraMessage() {
  localCameraMessageUntilAtMs = 0;
  localCameraScreenTitle = "";
  localCameraScreenMessage = "";
}

void showPreferredLocalScreen() {
  if (isServerMessageActive()) {
    return;
  }

  if (isLocalCameraMessageActive()) {
    showScreen(localCameraScreenTitle, localCameraScreenMessage);
    return;
  }

  showLocalSensorScreen();
}

void showLocalCameraMessage(const String &title,
                            const String &message,
                            unsigned long holdMs) {
  localCameraScreenTitle = title;
  localCameraScreenMessage = message;
  localCameraMessageUntilAtMs = millis() + holdMs;
  showPreferredLocalScreen();
}

void handleCameraAckDisplay(uint8_t status, const char *detail) {
  if (detail && *detail) {
    lastEspNowAckDetail = String(detail);
  }

  switch (status) {
    case ESPNOW_CAMERA_ACK_RECEIVED:
      showLocalCameraMessage("Camera ready",
                             "Queued",
                             PARKME_DISPLAY_CAMERA_QUEUED_HOLD_MS);
      break;
    case ESPNOW_CAMERA_ACK_CAPTURE_STARTED:
      showLocalCameraMessage("Taking photo",
                             "Please hold",
                             PARKME_DISPLAY_CAMERA_STARTED_HOLD_MS);
      break;
    case ESPNOW_CAMERA_ACK_CAPTURE_COMPLETED:
      showLocalCameraMessage("Photo sent",
                             "Checking plate",
                             PARKME_DISPLAY_CAMERA_COMPLETED_HOLD_MS);
      break;
    case ESPNOW_CAMERA_ACK_CAPTURE_FAILED:
      showLocalCameraMessage("Photo failed",
                             "Check dashboard",
                             PARKME_DISPLAY_CAMERA_FAILED_HOLD_MS);
      break;
    case ESPNOW_CAMERA_ACK_SPOT_FREED:
      clearLocalCameraMessage();
      showPreferredLocalScreen();
      break;
    default:
      break;
  }
}

unsigned long extractJsonUnsignedLongField(const String &payload,
                                           const char *fieldName,
                                           unsigned long fallbackValue) {
  String keyPattern = "\"";
  keyPattern += fieldName;
  keyPattern += "\"";

  int keyStart = payload.indexOf(keyPattern);
  if (keyStart < 0) {
    return fallbackValue;
  }

  int colonIndex = payload.indexOf(':', keyStart + keyPattern.length());
  if (colonIndex < 0) {
    return fallbackValue;
  }

  int valueStart = colonIndex + 1;
  while (valueStart < payload.length() &&
         isspace(static_cast<unsigned char>(payload[valueStart]))) {
    ++valueStart;
  }

  int valueEnd = valueStart;
  while (valueEnd < payload.length() &&
         isdigit(static_cast<unsigned char>(payload[valueEnd]))) {
    ++valueEnd;
  }

  if (valueEnd <= valueStart) {
    return fallbackValue;
  }

  return static_cast<unsigned long>(
      payload.substring(valueStart, valueEnd).toInt());
}

bool sendDisplayJsonRequest(const char *path,
                            const String &payload,
                            String &responseBody,
                            int &httpStatusCode) {
  WiFiClient plainClient;
  WiFiClientSecure secureClient;
  Client *client =
      String(PARKME_SERVER_SCHEME) == "https" ? &secureClient : &plainClient;
  secureClient.setInsecure();
  client->setTimeout(PARKME_DISPLAY_HTTP_TIMEOUT_MS);

  if (!client->connect(PARKME_SERVER_HOST, PARKME_SERVER_PORT)) {
    Serial.println("Display request cannot reach backend.");
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
         millis() - waitStartedAtMs < PARKME_DISPLAY_HTTP_TIMEOUT_MS) {
    delay(10);
  }

  if (!client->available()) {
    client->stop();
    Serial.println("Display backend response timeout.");
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
  return true;
}

bool pollDisplayCommand(String &requestId,
                        String &title,
                        String &message,
                        unsigned long &holdMs) {
  String payload = "{\"display_id\":\"";
  payload += PARKME_DISPLAY_ID;
  payload += "\"}";

  String responseBody;
  int httpStatusCode = -1;
  if (!sendDisplayJsonRequest(PARKME_API_DISPLAY_POLL_PATH,
                              payload,
                              responseBody,
                              httpStatusCode)) {
    return false;
  }

  if (httpStatusCode < 200 || httpStatusCode >= 300) {
    Serial.print("Display poll rejected with HTTP ");
    Serial.println(httpStatusCode);
    return false;
  }

  String action = extractJsonStringField(responseBody, "action");
  action.toUpperCase();
  if (action != "SHOW_MESSAGE") {
    return false;
  }

  requestId = extractJsonStringField(responseBody, "request_id");
  title = extractJsonStringField(responseBody, "title");
  message = extractJsonStringField(responseBody, "message");
  holdMs = extractJsonUnsignedLongField(responseBody, "hold_ms", 4000);
  return requestId.length() > 0;
}

void sendDisplayResult(const String &requestId,
                       const String &statusText,
                       const String &detail) {
  String payload = "{\"display_id\":\"";
  payload += PARKME_DISPLAY_ID;
  payload += "\",\"request_id\":\"";
  payload += requestId;
  payload += "\",\"status\":\"";
  payload += statusText;
  payload += "\",\"detail\":\"";
  payload += detail;
  payload += "\"}";

  String responseBody;
  int httpStatusCode = -1;
  if (!sendDisplayJsonRequest(PARKME_API_DISPLAY_RESULT_PATH,
                              payload,
                              responseBody,
                              httpStatusCode)) {
    Serial.println("Failed to acknowledge display command.");
    return;
  }

  Serial.print("Display ACK HTTP ");
  Serial.print(httpStatusCode);
  Serial.print(" | ");
  Serial.println(responseBody);
}

void handleDisplayPolling() {
  bool shouldRefreshScreen = false;

  if (activeMessageUntilAtMs > 0 &&
      static_cast<long>(millis() - activeMessageUntilAtMs) >= 0) {
    activeMessageUntilAtMs = 0;
    shouldRefreshScreen = true;
  }

  if (localCameraMessageUntilAtMs > 0 &&
      static_cast<long>(millis() - localCameraMessageUntilAtMs) >= 0) {
    clearLocalCameraMessage();
    shouldRefreshScreen = true;
  }

  if (shouldRefreshScreen) {
    showPreferredLocalScreen();
  }

  if (WiFi.status() != WL_CONNECTED) {
    return;
  }

  if (millis() - lastDisplayPollAtMs < PARKME_DISPLAY_COMMAND_POLL_INTERVAL_MS) {
    return;
  }

  lastDisplayPollAtMs = millis();

  String requestId;
  String title;
  String message;
  unsigned long holdMs = 4000;
  if (pollDisplayCommand(requestId, title, message, holdMs)) {
    Serial.print("Display command received: ");
    Serial.println(requestId);
    clearLocalCameraMessage();
    activeMessageUntilAtMs = millis() + holdMs;
    showScreen(title.length() > 0 ? title : "ParkMe", message);
    sendDisplayResult(requestId, "DISPLAYED", "rendered");
  }
}

float readDistanceCm() {
  digitalWrite(PARKME_SENSOR_TRIG_PIN, LOW);
  delayMicroseconds(2);

  digitalWrite(PARKME_SENSOR_TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(PARKME_SENSOR_TRIG_PIN, LOW);

  long durationUs = pulseIn(PARKME_SENSOR_ECHO_PIN, HIGH, kSensorEchoTimeoutUs);
  if (durationUs == 0) {
    return -1.0f;
  }

  return (durationUs * 0.0343f) / 2.0f;
}

bool calibrationButtonPressed() {
  if (PARKME_SENSOR_CALIBRATE_PIN < 0) {
    return false;
  }
  return digitalRead(PARKME_SENSOR_CALIBRATE_PIN) == LOW;
}

void persistPendingTelemetry() {
  preferences.putBytes("pending", &pendingTelemetry, sizeof(pendingTelemetry));
}

void clearPendingTelemetry() {
  pendingTelemetry.valid = 0;
  persistPendingTelemetry();
}

void queuePendingTelemetry(SpotState state, int batteryPercent) {
  pendingTelemetry.status = static_cast<uint8_t>(state);
  pendingTelemetry.batteryPercent =
      static_cast<uint8_t>(clampValue(batteryPercent, 0, 100));
  pendingTelemetry.valid = 1;
  persistPendingTelemetry();
}

void loadPendingTelemetry() {
  size_t loaded =
      preferences.getBytes("pending", &pendingTelemetry, sizeof(pendingTelemetry));
  if (loaded != sizeof(pendingTelemetry)) {
    pendingTelemetry = {0, 100, 0};
  }
}

void loadCalibration() {
  baselineDistanceCm =
      preferences.getFloat("base_cm", PARKME_SENSOR_DEFAULT_BASELINE_CM);
  occupiedThresholdCm = 20.0f;
}

void saveCalibration(float baselineCm) {
  baselineDistanceCm = baselineCm;
  occupiedThresholdCm = 20.0f;
  preferences.putFloat("base_cm", baselineDistanceCm);
}

float sampleAverageDistance(uint8_t sampleCount) {
  float total = 0.0f;
  uint8_t validSamples = 0;

  for (uint8_t i = 0; i < sampleCount; ++i) {
    float distanceCm = readDistanceCm();
    if (distanceCm > 0.0f && distanceCm <= kSensorMeasurementCapCm) {
      total += distanceCm;
      ++validSamples;
    }
    delay(120);
  }

  return validSamples == 0 ? -1.0f : (total / validSamples);
}

void runCalibrationMode() {
  Serial.println("Calibration mode started. Leave the parking spot empty.");
  float baselineCm = sampleAverageDistance(15);

  if (baselineCm <= 0.0f) {
    Serial.println("Calibration failed. Keeping previous baseline.");
    return;
  }

  saveCalibration(baselineCm);
  Serial.print("Baseline saved: ");
  Serial.print(baselineDistanceCm);
  Serial.print(" cm | Occupied threshold: ");
  Serial.print(occupiedThresholdCm);
  Serial.println(" cm");
}

float readBatteryVoltage() {
  if (PARKME_SENSOR_BATTERY_PIN < 0) {
    return PARKME_SENSOR_BATTERY_FULL_V;
  }

  uint32_t millivolts = analogReadMilliVolts(PARKME_SENSOR_BATTERY_PIN);
  float measuredVoltage = millivolts / 1000.0f;
  return measuredVoltage * PARKME_SENSOR_VOLTAGE_DIVIDER_RATIO;
}

int readBatteryPercent() {
  return batteryPercentFromVoltage(readBatteryVoltage(),
                                   PARKME_SENSOR_BATTERY_EMPTY_V,
                                   PARKME_SENSOR_BATTERY_FULL_V);
}

bool connectWiFi() {
  lastWifiAttemptAtMs = millis();

  showScreen("Connecting WiFi", "Please wait");
  Serial.print("Connecting to WiFi");
  WiFi.begin(PARKME_WIFI_SSID, PARKME_WIFI_PASSWORD);

  unsigned long startedAtMs = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - startedAtMs < 12000) {
    delay(400);
    Serial.print(".");
  }

  Serial.println();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("Connected. IP: ");
    Serial.println(WiFi.localIP());
    Serial.print("MAC: ");
    Serial.println(WiFi.macAddress());
    showLocalSensorScreen();
    return true;
  }

  Serial.println("WiFi connection failed.");
  showScreen("WiFi failed", "Retrying");
  return false;
}

void maintainWiFi() {
  if (WiFi.status() == WL_CONNECTED) {
    return;
  }

  unsigned long nowMs = millis();
  if (nowMs - lastWifiAttemptAtMs >= PARKME_SENSOR_WIFI_RETRY_INTERVAL_MS) {
    connectWiFi();
  }
}

bool postTelemetry(SpotState state, int batteryPercent) {
  if (WiFi.status() != WL_CONNECTED) {
    return false;
  }

  HTTPClient http;
  http.setTimeout(PARKME_SENSOR_HTTP_TIMEOUT_MS);

  String url =
      buildServerUrl(PARKME_SERVER_SCHEME,
                     PARKME_SERVER_HOST,
                     PARKME_SERVER_PORT,
                     PARKME_API_UPDATE_SPOT_PATH);
  WiFiClient plainClient;
  WiFiClientSecure secureClient;
  bool usingHttps = String(PARKME_SERVER_SCHEME).equalsIgnoreCase("https");
  bool beganRequest = false;

  if (usingHttps) {
    secureClient.setInsecure();
    beganRequest = http.begin(secureClient, url);
  } else {
    beganRequest = http.begin(plainClient, url);
  }

  if (!beganRequest) {
    Serial.println("HTTP begin failed.");
    return false;
  }

  http.addHeader("Content-Type", "application/json");
  String payload = makeHeartbeatPayload(WiFi.macAddress(),
                                        state,
                                        batteryPercent);

  int statusCode = http.POST(payload);
  String response = http.getString();
  http.end();

  Serial.print("POST ");
  Serial.print(payload);
  Serial.print(" -> ");
  Serial.print(statusCode);
  Serial.print(" | ");
  Serial.println(response);

  return statusCode >= 200 && statusCode < 300;
}

bool shouldSendTelemetry(SpotState currentState, unsigned long nowMs) {
  if (!isKnownState(currentState)) {
    return false;
  }

  if (!isKnownState(lastPublishedState)) {
    return true;
  }

  if (stateChanged(lastPublishedState, currentState)) {
    return true;
  }

  return shouldSendHeartbeat(currentState, PARKME_SENSOR_ALLOW_FREE_HEARTBEATS) &&
         (nowMs - lastSuccessfulPublishAtMs >=
          PARKME_SENSOR_HEARTBEAT_INTERVAL_MS);
}

float currentFreeDistanceLimitCm() {
  return computeFreeDistanceLimit(baselineDistanceCm,
                                  PARKME_SENSOR_MAX_RELIABLE_DISTANCE_CM,
                                  PARKME_SENSOR_OCCUPIED_DELTA_CM);
}

void markTelemetrySent(SpotState state) {
  lastPublishedState = state;
  lastSuccessfulPublishAtMs = millis();
}

void flushPendingTelemetry() {
  if (!pendingTelemetry.valid || WiFi.status() != WL_CONNECTED) {
    return;
  }

  SpotState pendingState = static_cast<SpotState>(pendingTelemetry.status);
  if (postTelemetry(pendingState, pendingTelemetry.batteryPercent)) {
    markTelemetrySent(pendingState);
    clearPendingTelemetry();
  }
}

void publishCurrentState(float distanceCm, SpotState state) {
  int batteryPercent = readBatteryPercent();
  SpotState previousState = lastMeasuredState;
  lastMeasuredDistanceCm = distanceCm;
  lastMeasuredState = state;
  lastMeasuredBatteryPercent = batteryPercent;

  Serial.print("Distance: ");
  Serial.print(distanceCm);
  Serial.print(" cm | Threshold: ");
  Serial.print(occupiedThresholdCm);
  Serial.print(" cm | Battery: ");
  Serial.print(batteryPercent);
  Serial.print("% | State: ");
  Serial.println(state == STATE_OCCUPIED ? "OCCUPIED" : "FREE");

  if (state == STATE_FREE && previousState != STATE_FREE) {
    clearLocalCameraMessage();
  }

  if (!isServerMessageActive() && !isLocalCameraMessageActive()) {
    showLocalSensorScreen();
  }

  sendEspNowState(state, batteryPercent);

  if (!shouldSendTelemetry(state, millis())) {
    return;
  }

  if (postTelemetry(state, batteryPercent)) {
    markTelemetrySent(state);
    clearPendingTelemetry();
  } else {
    queuePendingTelemetry(state, batteryPercent);
  }
}

void handleCalibrationButton() {
  if (!calibrationButtonPressed()) {
    calibrationButtonPressedAtMs = 0;
    return;
  }

  if (calibrationButtonPressedAtMs == 0) {
    calibrationButtonPressedAtMs = millis();
    return;
  }

  if (millis() - calibrationButtonPressedAtMs >= 4000) {
    calibrationButtonPressedAtMs = 0;
    runCalibrationMode();
  }
}

void setup() {
  Serial.begin(115200);
  delay(200);

  graphicsReady = beginGraphicsDisplay();
  showScreen("ParkMe", "Booting");

  pinMode(PARKME_SENSOR_TRIG_PIN, OUTPUT);
  pinMode(PARKME_SENSOR_ECHO_PIN, INPUT);

  if (PARKME_SENSOR_CALIBRATE_PIN >= 0) {
    pinMode(PARKME_SENSOR_CALIBRATE_PIN, INPUT_PULLUP);
  }

  if (PARKME_SENSOR_BATTERY_PIN >= 0) {
    analogReadResolution(12);
    analogSetPinAttenuation(PARKME_SENSOR_BATTERY_PIN, ADC_11db);
  }

  preferences.begin("parkme-node", false);
  loadCalibration();
  loadPendingTelemetry();

  Serial.println();
  Serial.println("ParkMe Sensor Node Started");
  Serial.print("MAC: ");
  Serial.println(WiFi.macAddress());
  Serial.print("Spot ID: ");
  Serial.println(PARKME_SENSOR_SPOT_ID);
  Serial.print("Backend: ");
  Serial.print(PARKME_SERVER_SCHEME);
  Serial.print("://");
  Serial.print(PARKME_SERVER_HOST);
  Serial.print(":");
  Serial.println(PARKME_SERVER_PORT);
  Serial.print("Loaded baseline: ");
  Serial.print(baselineDistanceCm);
  Serial.print(" cm | Threshold: ");
  Serial.print(occupiedThresholdCm);
  Serial.println(" cm");
  Serial.print("Display ID: ");
  Serial.println(PARKME_DISPLAY_ID);

  if (calibrationButtonPressed()) {
    runCalibrationMode();
  }

  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  espNowReady = initEspNow();
  connectWiFi();
}

void loop() {
  maintainWiFi();
  handleCalibrationButton();

  uint8_t pendingAckStatus = 0;
  char pendingAckDetail[24] = {0};
  if (takePendingEspNowAck(pendingAckStatus, pendingAckDetail)) {
    handleCameraAckDisplay(pendingAckStatus, pendingAckDetail);
  }

  if (millis() - lastSampleAtMs < PARKME_SENSOR_SAMPLE_INTERVAL_MS) {
    flushPendingTelemetry();
    handleDisplayPolling();
    return;
  }
  lastSampleAtMs = millis();

  float distanceCm = sampleAverageDistance(3);
  float freeDistanceLimitCm = currentFreeDistanceLimitCm();
  SpotState state = classifyDistanceCm(distanceCm,
                                       occupiedThresholdCm,
                                       freeDistanceLimitCm);

  if (!isKnownState(state)) {
    Serial.print("Sensor reading invalid. Distance: ");
    Serial.print(distanceCm);
    Serial.print(" cm | Free limit: ");
    Serial.print(freeDistanceLimitCm);
    Serial.print(" cm | Baseline: ");
    Serial.println(baselineDistanceCm);
    flushPendingTelemetry();
    handleDisplayPolling();
    return;
  }

  publishCurrentState(distanceCm, state);
  flushPendingTelemetry();
  handleDisplayPolling();
}
