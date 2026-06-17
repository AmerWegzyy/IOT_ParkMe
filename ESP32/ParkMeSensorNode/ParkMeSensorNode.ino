#include <HTTPClient.h>
#include <Preferences.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>

#include <ParkMeCommon.h>
#include <ParkMeConfig.h>

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
float occupiedThresholdCm = computeOccupiedThreshold(
    PARKME_SENSOR_DEFAULT_BASELINE_CM,
    PARKME_SENSOR_OCCUPIED_DELTA_CM,
    PARKME_SENSOR_MIN_THRESHOLD_CM);

SpotState lastPublishedState = STATE_UNKNOWN;
unsigned long lastSampleAtMs = 0;
unsigned long lastSuccessfulPublishAtMs = 0;
unsigned long lastWifiAttemptAtMs = 0;
unsigned long calibrationButtonPressedAtMs = 0;

}  // namespace

float readDistanceCm() {
  digitalWrite(PARKME_SENSOR_TRIG_PIN, LOW);
  delayMicroseconds(2);

  digitalWrite(PARKME_SENSOR_TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(PARKME_SENSOR_TRIG_PIN, LOW);

  long durationUs = pulseIn(PARKME_SENSOR_ECHO_PIN, HIGH, 30000);
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
  occupiedThresholdCm = computeOccupiedThreshold(
      baselineDistanceCm,
      PARKME_SENSOR_OCCUPIED_DELTA_CM,
      PARKME_SENSOR_MIN_THRESHOLD_CM);
}

void saveCalibration(float baselineCm) {
  baselineDistanceCm = baselineCm;
  occupiedThresholdCm = computeOccupiedThreshold(
      baselineDistanceCm,
      PARKME_SENSOR_OCCUPIED_DELTA_CM,
      PARKME_SENSOR_MIN_THRESHOLD_CM);
  preferences.putFloat("base_cm", baselineDistanceCm);
}

float sampleAverageDistance(uint8_t sampleCount) {
  float total = 0.0f;
  uint8_t validSamples = 0;

  for (uint8_t i = 0; i < sampleCount; ++i) {
    float distanceCm = readDistanceCm();
    if (distanceCm > 0.0f &&
        distanceCm <= PARKME_SENSOR_MAX_RELIABLE_DISTANCE_CM) {
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
    return true;
  }

  Serial.println("WiFi connection failed.");
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
  if (!http.begin(url)) {
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

  Serial.print("Distance: ");
  Serial.print(distanceCm);
  Serial.print(" cm | Threshold: ");
  Serial.print(occupiedThresholdCm);
  Serial.print(" cm | Battery: ");
  Serial.print(batteryPercent);
  Serial.print("% | State: ");
  Serial.println(state == STATE_OCCUPIED ? "OCCUPIED" : "FREE");

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
  Serial.print("Loaded baseline: ");
  Serial.print(baselineDistanceCm);
  Serial.print(" cm | Threshold: ");
  Serial.print(occupiedThresholdCm);
  Serial.println(" cm");

  if (calibrationButtonPressed()) {
    runCalibrationMode();
  }

  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  connectWiFi();
}

void loop() {
  maintainWiFi();
  flushPendingTelemetry();
  handleCalibrationButton();

  if (millis() - lastSampleAtMs < PARKME_SENSOR_SAMPLE_INTERVAL_MS) {
    return;
  }
  lastSampleAtMs = millis();

  float distanceCm = readDistanceCm();
  SpotState state = classifyDistanceCm(distanceCm,
                                       occupiedThresholdCm,
                                       PARKME_SENSOR_MAX_RELIABLE_DISTANCE_CM);

  if (!isKnownState(state)) {
    Serial.println("Sensor reading invalid. Skipping publish.");
    return;
  }

  publishCurrentState(distanceCm, state);
}
