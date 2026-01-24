//unit testing the sender part of the esp_now protocol
#include<WiFi.h>
#include<esp_wifi.h>
#include<esp_now.h>

//setting up the receiver MAC address
uint8_t receiverMac[] = {0xfc, 0xb4, 0x67, 0xf4, 0x58, 0xa8};

// Pins:
const int RIGHT_PIN = 33;
const int LEFT_PIN = 32;
const int DOWN_BUTTON = 25;
const int UP_BUTTON = 26;

// Foot ID's:
const uint8_t RIGHT = 1;
const uint8_t LEFT = 2;

// Protocol (packed):
enum MsgType : uint8_t { MSG_STEP = 1, MSG_BPM_DELTA = 2, MSG_CMD = 3 };

typedef struct __attribute__((packed)) {
  uint8_t type;
  union {
    struct __attribute__((packed)) {
       uint32_t intervalMS;
      uint8_t footId; 
    } step;
    struct __attribute__((packed)) {
      int8_t delta;
    } bpm;
    struct __attribute__((packed)) {
      uint8_t cmd;
      int16_t arg;
    } ctrl;
  };
} Packet;

// Control code
const uint8_t CMD_CAL_WEIGHT = 1;

// Step detection tuning (mutable after calibration):
// Per-sensor thresholds and baselines
int thresholdRight = 1200;
int thresholdLeft = 1200;
int baselineRight = 0;   // Resting state value
int baselineLeft = 0;    // Resting state value

// Pressure buffer as percentage of threshold (hysteresis)
const float PRESSURE_BUFFER_PERCENT = 0.55;  // 55% of threshold
int pressureBufferRight = 540;  // Will be recalculated in calibration
int pressureBufferLeft = 540;   // Will be recalculated in calibration

const uint32_t REFRACTORY_MS = 120;

uint32_t lastStepTime = 0;
uint32_t lastStepSentTime = 0;
bool leftFlag = false;
bool rightFlag = false;

// Control flags
volatile bool ctrlPending = false;
Packet ctrlPacket{};

// Button tuning (hold-repeat):
const uint32_t DEBOUNCE_MS = 25;
const uint32_t FIRST_REPEAT_DELAY_MS = 200;
const uint32_t REPEAT_RATE_MS = 60;

// Button state (minimal, robust)
struct Button {
  int pin;
  bool stable = HIGH;     // debounced state
  bool lastRaw = HIGH;    // last raw read
  uint32_t tChange = 0;   // last raw change time
  uint32_t tPress = 0;    // 0 = not pressed, else press start time
  uint32_t tRepeat = 0;   // last repeat tick time
  Button() = default;
  explicit Button(int p) : pin(p) {}
};

Button buttonUp(UP_BUTTON);
Button buttonDown(DOWN_BUTTON);

// ---------------- Helpers ----------------
inline void sendPacket(const Packet &p) {
  // Always send a fixed-size packet so receiver can parse easily
  esp_now_send(receiverMac, (const uint8_t*)&p, sizeof(Packet));
}

// ESP-NOW receive callback to catch control commands
void onDataRecv(const uint8_t* mac, const uint8_t* incomingData, int len) {
  if (len == (int)sizeof(Packet)) {
    Packet p;
    memcpy(&p, incomingData, sizeof(Packet));
    if (p.type == MSG_CMD) {
      ctrlPacket = p;
      ctrlPending = true;
    }
  }
}

// Calibration helper: sample both FSRs, set PER-SENSOR thresholds
int calibrateWeight(uint16_t samples = 200, uint16_t delayMs = 5, int margin = 150, int minThresh = 300) {
  long sumR = 0, sumL = 0;
  
  Serial.println("Calibrating... Stand normally on both sensors.");
  
  for (uint16_t i = 0; i < samples; i++) {
    sumR += analogRead(RIGHT_PIN);
    sumL += analogRead(LEFT_PIN);
    delay(delayMs);
  }
  
  int avgR = sumR / samples;
  int avgL = sumL / samples;
  
  // Store baselines (resting/standing state)
  baselineRight = avgR;
  baselineLeft = avgL;
  
  // Calculate individual thresholds: baseline - margin
  // This accounts for weaker sensors automatically
  thresholdRight = max(minThresh, avgR - margin);
  thresholdLeft = max(minThresh, avgL - margin);
  
  // Calculate pressure buffers as PERCENTAGE of threshold
  pressureBufferRight = (int)(thresholdRight * PRESSURE_BUFFER_PERCENT);
  pressureBufferLeft = (int)(thresholdLeft * PRESSURE_BUFFER_PERCENT);
  
  // Safety check: minimum buffer
  pressureBufferRight = max(200, pressureBufferRight);
  pressureBufferLeft = max(200, pressureBufferLeft);
  
  Serial.print("Right sensor - baseline: ");
  Serial.print(avgR);
  Serial.print(", threshold: ");
  Serial.print(thresholdRight);
  Serial.print(", buffer: ");
  Serial.println(pressureBufferRight);
  
  Serial.print("Left sensor - baseline: ");
  Serial.print(avgL);
  Serial.print(", threshold: ");
  Serial.print(thresholdLeft);
  Serial.print(", buffer: ");
  Serial.println(pressureBufferLeft);
  
  // Return average threshold for ACK
  return (thresholdRight + thresholdLeft) / 2;
}

// Send a control ACK/ERR back to receiver (arg can carry status or threshold)
void sendControlAck(uint8_t cmd, int16_t arg) {
  Packet resp{};
  resp.type = MSG_CMD;
  resp.ctrl.cmd = cmd;
  resp.ctrl.arg = arg;
  sendPacket(resp);
}

// Process pending control commands
void processControlIfPending() {
  if (!ctrlPending) return;
  noInterrupts();
  Packet p = ctrlPacket;
  ctrlPending = false;
  interrupts();

  if (p.ctrl.cmd == CMD_CAL_WEIGHT) {
    int margin = (int)p.ctrl.arg;
    if (margin <= 0) margin = 150;
    int newThresh = calibrateWeight(200, 5, margin);
    sendControlAck(CMD_CAL_WEIGHT, (int16_t)newThresh);  // Ack with new threshold value
  } else {
    sendControlAck(p.ctrl.cmd, (int16_t)-1); // Unknown command -> error
  }
}

// Fast time-based low-pass filter (IIR). 1 ADC read per loop.
int lowPass(int raw, int &state) {
  // 0.75*old + 0.25*new
  state = (state * 3 + raw) / 4;
  return state;
}

// Debounced pressed? (INPUT_PULLUP => LOW = pressed)
bool debouncedPressed(Button &b, uint32_t now) {
  bool raw = digitalRead(b.pin);
  if (raw != b.lastRaw) { b.lastRaw = raw; b.tChange = now; }
  if (now - b.tChange >= DEBOUNCE_MS) b.stable = raw;
  return (b.stable == LOW);
}

// BPM acceleration while holding (keeps network rate low but feels fast)
int8_t accelStep(uint32_t heldMs) {
  if (heldMs >= 2500) return 5;
  if (heldMs >= 1000) return 2;
  return 1;
}

void handleButton(Button &b, int8_t dir, uint32_t now) {
  bool pressed = debouncedPressed(b, now);

  // PRESS edge: immediate tick
  if (pressed && b.tPress == 0) {
    b.tPress = now;
    b.tRepeat = now;

    Packet p{};
    p.type = MSG_BPM_DELTA;
    p.bpm.delta = dir * 1;
    sendPacket(p);
    return;
  }

  // RELEASE edge
  if (!pressed && b.tPress != 0) {
    b.tPress = 0;
    return;
  }

  // HELD: rate-limited ticks
  if (pressed && b.tPress != 0) {
    uint32_t held = now - b.tPress;

    if (held >= FIRST_REPEAT_DELAY_MS && (now - b.tRepeat) >= REPEAT_RATE_MS) {
      int8_t step = accelStep(held);

      Packet p{};
      p.type = MSG_BPM_DELTA;
      p.bpm.delta = dir * step;
      sendPacket(p);

      b.tRepeat = now;
    }
  }
}

// Optional: keep send callback quiet to avoid jitter
void onDataSent(const uint8_t*, esp_now_send_status_t) {}

// ---------------- Setup ----------------
void setup() {
  Serial.begin(115200);

  // FSR analog inputs:
  pinMode(RIGHT_PIN, INPUT);
  pinMode(LEFT_PIN, INPUT);

  // Buttons:
  pinMode(DOWN_BUTTON, INPUT_PULLUP);
  pinMode(UP_BUTTON, INPUT_PULLUP);

  WiFi.mode(WIFI_STA);

  //initializing esp_now:
  if (esp_now_init() != ESP_OK) {
    Serial.println("Error initializing esp_now");
    return;
  }

  //configuring the sending protocol:
  esp_now_register_send_cb(onDataSent);

  esp_now_peer_info_t peerInfo = {};

  memcpy(peerInfo.peer_addr,receiverMac, 6);
  peerInfo.channel = 0;
  peerInfo.encrypt = false;

  if (esp_now_add_peer(&peerInfo) != ESP_OK) {
    Serial.println("Failed to add peer");
    return;
  }

  esp_now_register_recv_cb(onDataRecv);

  // Initial calibration on startup
  Serial.println("Starting initial calibration in 2 seconds...");
  Serial.println("Please stand normally on BOTH sensors.");
  delay(2000);
  calibrateWeight(200, 5, 200);  // Increased margin to 200 for less sensitivity
  
  Serial.println("\nCalibration complete. Ready to send.");
}

// ---------------- Loop ----------------
void loop() {
  // Getting the current time:
  uint32_t now =  millis();

  // Handle inbound control commands (e.g., calibration)
  processControlIfPending();

  // Buttons:
  bool upRaw = (digitalRead(UP_BUTTON) == LOW);
  bool downRaw = (digitalRead(DOWN_BUTTON) == LOW);
  // Safety: if both pressed, ignore
  if (!(upRaw && downRaw)) {
    handleButton(buttonUp, +1, now);
    handleButton(buttonDown, -1, now);
  }

  // FSR read + filtering:
  static int rState = 0, lState = 0;
  int rightFsr = lowPass(analogRead(RIGHT_PIN), rState);
  int leftFsr  = lowPass(analogRead(LEFT_PIN),  lState);

  // Flag reset (per-sensor thresholds with percentage-based buffers):
  if (rightFsr <= thresholdRight - pressureBufferRight) 
    rightFlag = false;
  if (leftFsr  <= thresholdLeft - pressureBufferLeft) 
    leftFlag  = false;

  // New step detection:
  bool stepDetected = false;
  int stepFootId = 0;
  int triggeredFsr = 0;

  // Checking if there is pressure on the sensors (per-sensor thresholds)
  if(!rightFlag && rightFsr > thresholdRight){
    rightFlag = true;
    stepDetected = true;
    stepFootId = 1;
    triggeredFsr = rightFsr;
  }
  if(!leftFlag && leftFsr > thresholdLeft){
    leftFlag = true;
    stepDetected = true;
    stepFootId = 2;
    triggeredFsr = leftFsr;
  }

  // Refractory guard + send
  if (stepDetected && (now - lastStepSentTime) >= REFRACTORY_MS) {
    lastStepSentTime = now;

    Packet p{};
    p.type = MSG_STEP;
    p.step.intervalMS = now - lastStepTime;
    lastStepTime = now;
    p.step.footId = stepFootId;            

    // Sending step event:
    Serial.println(triggeredFsr);
    
    sendPacket(p);
    Serial.println("sent");
  }
}
