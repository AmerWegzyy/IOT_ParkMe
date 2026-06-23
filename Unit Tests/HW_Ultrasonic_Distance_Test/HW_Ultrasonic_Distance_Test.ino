#include <Arduino.h>

namespace {

// Same hardware values as ESP32/SECRETS.h. Kept local so Arduino IDE can open
// this HW test directly from the submitted Unit Tests folder.
constexpr uint8_t PARKME_SENSOR_TRIG_PIN = 5;
constexpr uint8_t PARKME_SENSOR_ECHO_PIN = 18;
constexpr float PARKME_SENSOR_DEFAULT_BASELINE_CM = 80.0f;
constexpr float PARKME_SENSOR_OCCUPIED_DELTA_CM = 30.0f;
constexpr float PARKME_SENSOR_MIN_THRESHOLD_CM = 8.0f;
constexpr float PARKME_SENSOR_MAX_RELIABLE_DISTANCE_CM = 350.0f;
constexpr uint8_t SAMPLE_COUNT = 10;
constexpr float MIN_VALID_DISTANCE_CM = 2.0f;

enum SpotState {
  STATE_UNKNOWN = 0,
  STATE_FREE = 1,
  STATE_OCCUPIED = 2,
};

float computeOccupiedThreshold(float baselineCm,
                               float occupiedDeltaCm,
                               float minimumThresholdCm) {
  float threshold = baselineCm - occupiedDeltaCm;
  return threshold < minimumThresholdCm ? minimumThresholdCm : threshold;
}

SpotState classifyDistanceCm(float distanceCm,
                             float occupiedThresholdCm,
                             float maxReliableDistanceCm) {
  if (distanceCm <= 0.0f || distanceCm > maxReliableDistanceCm) {
    return STATE_UNKNOWN;
  }
  return distanceCm <= occupiedThresholdCm ? STATE_OCCUPIED : STATE_FREE;
}

float readDistanceCm() {
  digitalWrite(PARKME_SENSOR_TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(PARKME_SENSOR_TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(PARKME_SENSOR_TRIG_PIN, LOW);

  unsigned long durationUs = pulseIn(PARKME_SENSOR_ECHO_PIN, HIGH, 30000);
  if (durationUs == 0) {
    return -1.0f;
  }

  return (durationUs * 0.0343f) / 2.0f;
}

float readAverageDistanceCm() {
  float total = 0.0f;
  uint8_t validSamples = 0;

  for (uint8_t i = 0; i < SAMPLE_COUNT; ++i) {
    float distanceCm = readDistanceCm();
    if (distanceCm >= MIN_VALID_DISTANCE_CM &&
        distanceCm <= PARKME_SENSOR_MAX_RELIABLE_DISTANCE_CM) {
      total += distanceCm;
      ++validSamples;
    }
    delay(100);
  }

  if (validSamples == 0) {
    return -1.0f;
  }

  return total / validSamples;
}

void printResult(float distanceCm) {
  Serial.print("Distance average: ");
  Serial.print(distanceCm);
  Serial.print(" cm | Threshold: ");
  Serial.print(computeOccupiedThreshold(PARKME_SENSOR_DEFAULT_BASELINE_CM,
                                        PARKME_SENSOR_OCCUPIED_DELTA_CM,
                                        PARKME_SENSOR_MIN_THRESHOLD_CM));
  Serial.print(" cm | Result: ");

  if (distanceCm < 0.0f) {
    Serial.println("FAIL - no echo received");
    return;
  }

  SpotState state = classifyDistanceCm(
      distanceCm,
      computeOccupiedThreshold(PARKME_SENSOR_DEFAULT_BASELINE_CM,
                               PARKME_SENSOR_OCCUPIED_DELTA_CM,
                               PARKME_SENSOR_MIN_THRESHOLD_CM),
      PARKME_SENSOR_MAX_RELIABLE_DISTANCE_CM);

  if (state == STATE_UNKNOWN) {
    Serial.println("FAIL - invalid distance");
    return;
  }

  Serial.print("PASS - sensor is reading, classified as ");
  Serial.println(state == STATE_OCCUPIED ? "OCCUPIED" : "FREE");
}

}  // namespace

void setup() {
  Serial.begin(115200);
  delay(1000);

  pinMode(PARKME_SENSOR_TRIG_PIN, OUTPUT);
  pinMode(PARKME_SENSOR_ECHO_PIN, INPUT);

  Serial.println();
  Serial.println("HW TEST: HC-SR04 ultrasonic distance sensor");
  Serial.print("TRIG pin: ");
  Serial.println(PARKME_SENSOR_TRIG_PIN);
  Serial.print("ECHO pin: ");
  Serial.println(PARKME_SENSOR_ECHO_PIN);
  Serial.println("Move an object in front of the sensor and watch readings.");
}

void loop() {
  printResult(readAverageDistanceCm());
  delay(1000);
}
