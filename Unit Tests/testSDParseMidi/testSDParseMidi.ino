#include <SD.h>
#include <SPI.h>
#include <Adafruit_NeoPixel.h>

// =======================
// 1. NEOPIXEL SETTINGS
// =======================
#define NEO_PIN        14   // Pin connected to NeoPixels
#define NUMPIXELS      126 
Adafruit_NeoPixel pixels(NUMPIXELS, NEO_PIN, NEO_GRB + NEO_KHZ800);

// Key mapping settings
#define KEY_SHIFT 36
#define FIRST_KEY 36
#define LAST_KEY  96

// LED Map from your file
int listOfLEDsByKey[][3] = {
  {2,3,-1},{4,5,-1},{6,7,-1},{8,9,-1},{10,11,-1},{12,13,-1},
  {14,15,-1},{16,17,-1},{18,19,-1},{20,21,-1},{22,23,-1},{24,25,-1},
  {26,27,-1},{28,29,-1},{30,31,-1},{32,33,-1},{34,35,-1},{36,37,-1},
  {38,39,-1},{40,41,-1},{42,-1,-1},{43,44,45},{46,-1,-1},{47,48,-1},
  {49,50,-1},{51,52,-1},{53,54,-1},{55,56,-1},{57,58,-1},{59,60,-1},
  {61,62,-1},{63,64,-1},{65,66,-1},{67,68,-1},{69,70,-1},{71,-1,-1},
  {72,73,-1},{74,75,-1},{76,77,-1},{78,79,-1},{80,81,-1},{82,83,-1},
  {84,85,-1},{86,87,-1},{88,89,-1},{90,91,-1},{92,93,-1},{94,95,-1},
  {96,97,-1},{98,99,-1},{100,101,-1},{102,103,-1},{104,105,-1},
  {106,107,-1},{108,109,-1},{110,111,-1},{112,113,-1},{114,115,-1},
  {116,117,-1},{118,119,-1},{120,121,122},{123,124,125}
};

// =======================
// 2. LED HELPERS
// =======================
void lightLEDsByKey(int key, uint32_t color) {
  int index = key - KEY_SHIFT;
  // Safety check
  if (index < 0 || index >= (sizeof(listOfLEDsByKey)/sizeof(listOfLEDsByKey[0]))) return;

  for (int i=0; i<3; i++) {
    int led = listOfLEDsByKey[index][i];
    if (led != -1) pixels.setPixelColor(led, color);
  }
  pixels.show();
}

void handleNoteOn(uint8_t ch, uint8_t note, uint8_t vel) {
  Serial.printf("NoteOn: %d\n", note);
  lightLEDsByKey(note, pixels.Color(0, 180, 0)); // Green
}

void handleNoteOff(uint8_t ch, uint8_t note, uint8_t vel) {
  lightLEDsByKey(note, 0); // Turn off
}

// =======================
// 3. MIDI HELPERS
// =======================
uint32_t readVLQ(File &f) {
  uint32_t value = 0;
  uint8_t c;
  do {
    c = f.read();
    value = (value << 7) | (c & 0x7F);
  } while (c & 0x80);
  return value;
}

// =======================
// 4. MAIN SETUP
// =======================
void setup() {
  Serial.begin(115200);
  
  // Init LEDs
  pixels.begin();
  pixels.clear();
  pixels.show();

  // Init SD
  if (!SD.begin(5)) {
    Serial.println("SD mount failed!");
    return;
  }

  File f = SD.open("/test1.mid");
  if (!f) {
    Serial.println("Cannot open test1.mid");
    return;
  }

  // --- Read Header ---
  uint8_t hdr[4]; 
  f.read(hdr, 4); // "MThd"
  uint32_t hdrLen = f.read() << 24 | f.read() << 16 | f.read() << 8 | f.read();
  uint16_t format = f.read() << 8 | f.read();
  uint16_t nTracks = f.read() << 8 | f.read();
  uint16_t division = f.read() << 8 | f.read();

  Serial.printf("Fmt=%d Trks=%d Div=%d\n", format, nTracks, division);

  // --- Loop Tracks ---
  for (int t = 0; t < nTracks; t++) {
    Serial.printf("Track %d\n", t + 1);
    
    // Read "MTrk"
    f.read(hdr, 4); 
    // Track Length
    uint32_t trackLen = f.read() << 24 | f.read() << 16 | f.read() << 8 | f.read();
    uint32_t trackEnd = f.position() + trackLen;

    uint8_t runningStatus = 0;

    while (f.position() < trackEnd) {
      uint32_t delta = readVLQ(f);
      
      // === TIMING HACK ===
      // Without this, the song plays instantly.
      // Assuming approx 1ms per tick for simplicity.
      if (delta > 0) delay(delta); 
      // ===================

      uint8_t status = f.peek();

      if (status < 0x80) {
        status = runningStatus;
      } else {
        status = f.read();
        runningStatus = status;
      }

      uint8_t cmd = status & 0xF0;
      uint8_t ch  = status & 0x0F;

      if (cmd == 0x90) { // Note On
        uint8_t note = f.read();
        uint8_t vel  = f.read();
        if (vel == 0) handleNoteOff(ch, note, vel);
        else          handleNoteOn(ch, note, vel);
      }
      else if (cmd == 0x80) { // Note Off
        uint8_t note = f.read();
        uint8_t vel  = f.read();
        handleNoteOff(ch, note, vel);
      }
      else if (status == 0xFF) { // Meta
        f.read(); // Skip Type
        uint32_t len = readVLQ(f);
        f.seek(f.position() + len);
      }
      else if (status == 0xF0 || status == 0xF7) { // Sysex
        uint32_t len = readVLQ(f);
        f.seek(f.position() + len);
      }
      else {
        // Other events (Program Change, Control Change, etc)
        if (cmd == 0xC0 || cmd == 0xD0) f.read();
        else { f.read(); f.read(); }
      }
    }
  }
  Serial.println("Done.");
  pixels.clear();
  pixels.show();
}

void loop() {}