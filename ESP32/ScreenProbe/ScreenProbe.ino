#include <Arduino.h>
#include <Wire.h>

#if __has_include(<U8g2lib.h>)
#include <U8g2lib.h>
#define SCREEN_PROBE_HAS_U8G2 1
#else
#define SCREEN_PROBE_HAS_U8G2 0
#endif

namespace {

constexpr uint8_t kSdaPin = 21;
constexpr uint8_t kSclPin = 22;
constexpr uint32_t kSerialBaud = 115200;

#if SCREEN_PROBE_HAS_U8G2
U8G2_SSD1306_128X64_NONAME_F_HW_I2C probeSsd1306(U8G2_R0, U8X8_PIN_NONE);
U8G2_SH1106_128X64_NONAME_F_HW_I2C probeSh1106(U8G2_R0, U8X8_PIN_NONE);
#endif

uint8_t detectedAddresses[8] = {0};
uint8_t detectedCount = 0;

}  // namespace

void printHexAddress(uint8_t address) {
  Serial.print("0x");
  if (address < 16) {
    Serial.print('0');
  }
  Serial.print(address, HEX);
}

void scanI2cBus() {
  detectedCount = 0;

  Serial.println();
  Serial.print("Scanning I2C bus on SDA=");
  Serial.print(kSdaPin);
  Serial.print(" SCL=");
  Serial.println(kSclPin);

  for (uint8_t address = 1; address < 127; ++address) {
    Wire.beginTransmission(address);
    uint8_t error = Wire.endTransmission();
    if (error == 0) {
      if (detectedCount < sizeof(detectedAddresses)) {
        detectedAddresses[detectedCount++] = address;
      }
      Serial.print("Found I2C device at ");
      printHexAddress(address);
      Serial.println();
    }
  }

  if (detectedCount == 0) {
    Serial.println("No I2C devices found.");
  }
}

#if SCREEN_PROBE_HAS_U8G2
void drawProbeScreen(U8G2 &display,
                     const char *driverName,
                     uint8_t address,
                     const char *line2) {
  display.clearBuffer();
  display.setFont(u8g2_font_ncenB08_tr);
  display.drawUTF8(0, 14, "ParkMe Probe");
  display.drawLine(0, 18, 127, 18);
  display.setFont(u8g2_font_6x12_tf);
  display.drawUTF8(0, 34, driverName);

  char addressBuffer[16];
  snprintf(addressBuffer, sizeof(addressBuffer), "Addr 0x%02X", address);
  display.drawUTF8(0, 48, addressBuffer);
  display.drawUTF8(0, 62, line2);
  display.sendBuffer();
}

void tryDisplay(U8G2 &display, const char *driverName, uint8_t address) {
  Serial.print("Trying ");
  Serial.print(driverName);
  Serial.print(" at ");
  printHexAddress(address);
  Serial.println();

  display.setI2CAddress(address << 1);
  display.begin();
  display.setPowerSave(0);

  drawProbeScreen(display, driverName, address, "If visible, it works");
  delay(5000);

  drawProbeScreen(display, driverName, address, "Watch serial too");
  delay(3000);
}
#endif

void setup() {
  Serial.begin(kSerialBaud);
  delay(300);

  Serial.println();
  Serial.println("ParkMe Screen Probe Started");

  Wire.begin(kSdaPin, kSclPin);
  Wire.setClock(100000);
  scanI2cBus();

#if SCREEN_PROBE_HAS_U8G2
  if (detectedCount == 0) {
    Serial.println("Nothing to test because no I2C display was detected.");
    return;
  }

  for (uint8_t i = 0; i < detectedCount; ++i) {
    uint8_t address = detectedAddresses[i];
    tryDisplay(probeSsd1306, "SSD1306", address);
    tryDisplay(probeSh1106, "SH1106", address);
  }

  Serial.println("Probe cycle complete. Reset the board to run it again.");
#else
  Serial.println("U8g2 library not found. Install 'U8g2' in Arduino IDE first.");
#endif
}

void loop() {
  delay(1000);
}
