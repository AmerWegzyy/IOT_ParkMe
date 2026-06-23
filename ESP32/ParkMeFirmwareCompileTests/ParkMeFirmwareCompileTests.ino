#include <ParkMeCommon.h>

using namespace parkme;

static_assert(clampValue(12, 0, 10) == 10, "Clamp should cap high values.");
static_assert(clampValue(-3, 0, 10) == 0, "Clamp should cap low values.");
static_assert(computeOccupiedThreshold(80.0f, 30.0f, 8.0f) == 50.0f,
              "Threshold should be baseline minus delta.");
static_assert(computeOccupiedThreshold(20.0f, 30.0f, 8.0f) == 8.0f,
              "Threshold should honor the floor.");
static_assert(computeFreeDistanceLimit(390.0f, 350.0f, 30.0f) == 420.0f,
              "Free-distance limit should expand to cover the calibrated floor.");
static_assert(computeFreeDistanceLimit(80.0f, 350.0f, 30.0f) == 350.0f,
              "Free-distance limit should preserve the configured ceiling when adequate.");
static_assert(classifyDistanceCm(18.0f, 20.0f, 350.0f) == STATE_OCCUPIED,
              "Near objects should mark the spot occupied.");
static_assert(classifyDistanceCm(42.0f, 20.0f, 350.0f) == STATE_FREE,
              "Far objects should mark the spot free.");
static_assert(classifyDistanceCm(-1.0f, 20.0f, 350.0f) == STATE_UNKNOWN,
              "Invalid negative readings should be unknown.");
static_assert(batteryPercentFromVoltage(4.2f, 3.2f, 4.2f) == 100,
              "Full battery should map to 100 percent.");
static_assert(batteryPercentFromVoltage(3.2f, 3.2f, 4.2f) == 0,
              "Empty battery should map to 0 percent.");
static_assert(shouldSendHeartbeat(STATE_OCCUPIED, false),
              "Occupied spots should still heartbeat.");
static_assert(!shouldSendHeartbeat(STATE_FREE, false),
              "Free heartbeats can be disabled.");
static_assert(parseGateAction("{\"action\":\"WELCOME\"}") == ACTION_WELCOME,
              "WELCOME payload should parse.");
static_assert(parseGateAction("{\"action\":\"DENIED\"}") == ACTION_DENIED,
              "DENIED payload should parse.");
static_assert(parseGateAction("{\"action\":\"RETRY\"}") == ACTION_RETRY,
              "RETRY payload should parse.");
static_assert(parseGateAction("{\"status\":\"ok\"}") == ACTION_UNKNOWN,
              "Unknown payloads should stay unknown.");

void setup() {}

void loop() {}
