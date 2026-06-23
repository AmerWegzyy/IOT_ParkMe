#ifndef PARKME_COMMON_H
#define PARKME_COMMON_H

#include <Arduino.h>
#include <ctype.h>

namespace parkme {

enum SpotState : uint8_t {
  STATE_FREE = 0,
  STATE_OCCUPIED = 1,
  STATE_UNKNOWN = 255
};

enum GateAction : uint8_t {
  ACTION_UNKNOWN = 0,
  ACTION_WELCOME = 1,
  ACTION_DENIED = 2,
  ACTION_RETRY = 3
};

template <typename T>
constexpr T clampValue(T value, T minimum, T maximum) {
  return value < minimum ? minimum : (value > maximum ? maximum : value);
}

constexpr int roundToNearestInt(float value) {
  return value >= 0.0f ? static_cast<int>(value + 0.5f)
                       : static_cast<int>(value - 0.5f);
}

constexpr float computeOccupiedThreshold(float baselineCm,
                                         float occupiedDeltaCm,
                                         float minThresholdCm) {
  return (baselineCm - occupiedDeltaCm) < minThresholdCm
             ? minThresholdCm
             : (baselineCm - occupiedDeltaCm);
}

constexpr float computeFreeDistanceLimit(float baselineCm,
                                         float maxReliableDistanceCm,
                                         float fallbackBufferCm) {
  return baselineCm <= 0.0f
             ? maxReliableDistanceCm
             : ((baselineCm + fallbackBufferCm) > maxReliableDistanceCm
                    ? (baselineCm + fallbackBufferCm)
                    : maxReliableDistanceCm);
}

constexpr SpotState classifyDistanceCm(float distanceCm,
                                       float occupiedThresholdCm,
                                       float maxReliableDistanceCm) {
  return (distanceCm <= 0.0f || distanceCm > maxReliableDistanceCm)
             ? STATE_UNKNOWN
             : (distanceCm <= occupiedThresholdCm ? STATE_OCCUPIED
                                                  : STATE_FREE);
}

constexpr bool isKnownState(SpotState state) {
  return state == STATE_FREE || state == STATE_OCCUPIED;
}

constexpr bool stateChanged(SpotState previous, SpotState current) {
  return isKnownState(previous) && isKnownState(current) && previous != current;
}

constexpr int batteryPercentFromVoltage(float batteryVoltage,
                                        float emptyVoltage,
                                        float fullVoltage) {
  return fullVoltage <= emptyVoltage
             ? 0
             : clampValue(
                   roundToNearestInt(
                       ((batteryVoltage - emptyVoltage) * 100.0f) /
                       (fullVoltage - emptyVoltage)),
                   0,
                   100);
}

constexpr bool shouldSendHeartbeat(SpotState state, bool allowFreeHeartbeats) {
  return state == STATE_OCCUPIED || allowFreeHeartbeats;
}

constexpr bool startsWithLiteral(const char *text, const char *token) {
  return *token == '\0'
             ? true
             : (*text == '\0'
                    ? false
                    : (*text == *token &&
                       startsWithLiteral(text + 1, token + 1)));
}

constexpr bool containsLiteral(const char *text, const char *token) {
  return *token == '\0'
             ? true
             : (*text == '\0'
                    ? false
                    : (startsWithLiteral(text, token) ||
                       containsLiteral(text + 1, token)));
}

constexpr GateAction parseGateAction(const char *payload) {
  return containsLiteral(payload, "\"action\":\"WELCOME\"")
             ? ACTION_WELCOME
             : (containsLiteral(payload, "\"action\":\"DENIED\"")
                    ? ACTION_DENIED
                    : (containsLiteral(payload, "\"action\":\"RETRY\"")
                           ? ACTION_RETRY
                           : ACTION_UNKNOWN));
}

inline String buildServerUrl(const char *scheme,
                             const char *host,
                             uint16_t port,
                             const char *path) {
  String url = scheme;
  url += "://";
  url += host;
  bool defaultPort = (String(scheme) == "http" && port == 80) ||
                     (String(scheme) == "https" && port == 443);
  if (!defaultPort) {
    url += ":";
    url += String(port);
  }
  url += path;
  return url;
}

inline String buildServerUrl(const char *host, uint16_t port, const char *path) {
  return buildServerUrl("http", host, port, path);
}


inline String makeHeartbeatPayload(const String &macAddress,
                                   SpotState state,
                                   int batteryPercent) {
  String payload = "{\"mac_address\":\"";
  payload += macAddress;
  payload += "\",\"is_occupied\":";
  payload += state == STATE_OCCUPIED ? "true" : "false";
  payload += ",\"battery_level\":";
  payload += String(batteryPercent);
  payload += "}";
  return payload;
}

inline String extractJsonStringField(const String &payload,
                                     const char *fieldName) {
  String keyPattern = "\"";
  keyPattern += fieldName;
  keyPattern += "\"";

  int keyStart = payload.indexOf(keyPattern);
  if (keyStart < 0) {
    return "";
  }

  int colonIndex = payload.indexOf(':', keyStart + keyPattern.length());
  if (colonIndex < 0) {
    return "";
  }

  int valueStart = colonIndex + 1;
  while (valueStart < payload.length() &&
         isspace(static_cast<unsigned char>(payload[valueStart]))) {
    ++valueStart;
  }

  if (valueStart >= payload.length() || payload[valueStart] != '"') {
    return "";
  }

  ++valueStart;
  int valueEnd = valueStart;
  while (valueEnd < payload.length()) {
    if (payload[valueEnd] == '"' && payload[valueEnd - 1] != '\\') {
      break;
    }
    ++valueEnd;
  }

  if (valueEnd >= payload.length()) {
    return "";
  }

  String value = payload.substring(valueStart, valueEnd);
  value.replace("\\\"", "\"");
  value.replace("\\n", " ");
  return value;
}

inline GateAction parseGateAction(const String &payload) {
  String action = extractJsonStringField(payload, "action");
  action.toUpperCase();

  if (action == "WELCOME") {
    return ACTION_WELCOME;
  }
  if (action == "DENIED") {
    return ACTION_DENIED;
  }
  if (action == "RETRY") {
    return ACTION_RETRY;
  }

  return ACTION_UNKNOWN;
}

inline String extractGateMessage(const String &payload) {
  String message = extractJsonStringField(payload, "message");
  if (message.length() > 0) {
    return message;
  }

  return extractJsonStringField(payload, "display_message");
}

inline int parseHttpStatusCode(const String &statusLine) {
  int firstSpace = statusLine.indexOf(' ');
  if (firstSpace < 0) {
    return -1;
  }

  int secondSpace = statusLine.indexOf(' ', firstSpace + 1);
  String code =
      secondSpace > firstSpace
          ? statusLine.substring(firstSpace + 1, secondSpace)
          : statusLine.substring(firstSpace + 1);
  return code.toInt();
}

inline String fitForLcd(const String &text, size_t width) {
  if (text.length() <= width) {
    return text;
  }
  return text.substring(0, width);
}

}  // namespace parkme

#endif
