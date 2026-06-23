#include <Arduino.h>
#include <Wire.h>

// Hardware unit test for a 4-pin I2C OLED marked VCC, GND, SCK, SDA.
// This no-library driver uses page addressing and works with many
// SSD1306 and SH1106 OLED modules.
//
// ESP32 DevKit wiring:
//   OLED VCC -> 3V3
//   OLED GND -> GND
//   OLED SDA -> GPIO21
//   OLED SCK -> GPIO22
constexpr uint8_t OLED_SDA_PIN = 21;
constexpr uint8_t OLED_SCL_PIN = 22;
constexpr uint8_t OLED_ADDRESS = 0x3C;
constexpr uint8_t OLED_WIDTH = 128;
constexpr uint8_t OLED_HEIGHT = 64;
constexpr uint8_t OLED_PAGES = OLED_HEIGHT / 8;

// SH1106 modules usually need +2. SSD1306 modules usually use 0.
// If text is shifted too far right, change this to 0 and upload again.
constexpr uint8_t OLED_COLUMN_OFFSET = 2;

uint8_t displayBuffer[OLED_WIDTH * OLED_PAGES];

const uint8_t FONT_SPACE[5] = {0x00, 0x00, 0x00, 0x00, 0x00};
const uint8_t FONT_A[5] = {0x7E, 0x11, 0x11, 0x11, 0x7E};
const uint8_t FONT_C[5] = {0x3E, 0x41, 0x41, 0x41, 0x22};
const uint8_t FONT_E[5] = {0x7F, 0x49, 0x49, 0x49, 0x41};
const uint8_t FONT_K[5] = {0x7F, 0x08, 0x14, 0x22, 0x41};
const uint8_t FONT_L[5] = {0x7F, 0x40, 0x40, 0x40, 0x40};
const uint8_t FONT_M[5] = {0x7F, 0x02, 0x0C, 0x02, 0x7F};
const uint8_t FONT_O[5] = {0x3E, 0x41, 0x41, 0x41, 0x3E};
const uint8_t FONT_P[5] = {0x7F, 0x09, 0x09, 0x09, 0x06};
const uint8_t FONT_R[5] = {0x7F, 0x09, 0x19, 0x29, 0x46};
const uint8_t FONT_T[5] = {0x01, 0x01, 0x7F, 0x01, 0x01};
const uint8_t FONT_W[5] = {0x7F, 0x20, 0x18, 0x20, 0x7F};

const uint8_t *fontFor(char c) {
  switch (c) {
    case 'A': return FONT_A;
    case 'C': return FONT_C;
    case 'E': return FONT_E;
    case 'K': return FONT_K;
    case 'L': return FONT_L;
    case 'M': return FONT_M;
    case 'O': return FONT_O;
    case 'P': return FONT_P;
    case 'R': return FONT_R;
    case 'T': return FONT_T;
    case 'W': return FONT_W;
    default: return FONT_SPACE;
  }
}

void oledCommand(uint8_t command) {
  Wire.beginTransmission(OLED_ADDRESS);
  Wire.write(0x00);
  Wire.write(command);
  Wire.endTransmission();
}

void oledData(const uint8_t *data, uint8_t length) {
  Wire.beginTransmission(OLED_ADDRESS);
  Wire.write(0x40);
  for (uint8_t i = 0; i < length; ++i) {
    Wire.write(data[i]);
  }
  Wire.endTransmission();
}

bool oledAddressResponds() {
  Wire.beginTransmission(OLED_ADDRESS);
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
  for (uint8_t page = 0; page < OLED_PAGES; ++page) {
    uint8_t column = OLED_COLUMN_OFFSET;
    oledCommand(0xB0 + page);
    oledCommand(0x00 + (column & 0x0F));
    oledCommand(0x10 + ((column >> 4) & 0x0F));

    const uint8_t *pageData = &displayBuffer[page * OLED_WIDTH];
    for (uint8_t x = 0; x < OLED_WIDTH; x += 16) {
      oledData(&pageData[x], 16);
    }
  }
}

void setPixel(uint8_t x, uint8_t y, bool enabled) {
  if (x >= OLED_WIDTH || y >= OLED_HEIGHT) {
    return;
  }

  uint16_t index = x + (y / 8) * OLED_WIDTH;
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

void drawText(uint8_t x, uint8_t y, const char *text, uint8_t scale) {
  uint8_t cursorX = x;
  while (*text) {
    drawChar(cursorX, y, *text, scale);
    cursorX += 6 * scale;
    ++text;
  }
}

void showWelcome() {
  memset(displayBuffer, 0, sizeof(displayBuffer));
  drawText(14, 12, "WELCOME", 2);
  drawText(34, 44, "PARKME", 1);
  oledDisplay();
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println();
  Serial.println("HW TEST: I2C OLED SSD1306/SH1106 display");
  Serial.print("SDA pin: ");
  Serial.println(OLED_SDA_PIN);
  Serial.print("SCK/SCL pin: ");
  Serial.println(OLED_SCL_PIN);
  Serial.print("OLED address: 0x");
  Serial.println(OLED_ADDRESS, HEX);

  Wire.begin(OLED_SDA_PIN, OLED_SCL_PIN);

  if (!oledAddressResponds()) {
    Serial.println("FAIL - OLED I2C address did not respond");
    Serial.println("Check VCC, GND, SDA, SCK/SCL wires or try address 0x3D.");
    return;
  }

  Serial.println("PASS - OLED I2C address responded");
  oledInit();
  showWelcome();
  Serial.println("PASS - OLED initialized and WELCOME text displayed");
}

void loop() {
  // Keep WELCOME on the screen permanently.
  delay(1000);
}
