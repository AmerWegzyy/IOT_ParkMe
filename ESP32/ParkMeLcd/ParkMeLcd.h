#ifndef PARKME_LCD_H
#define PARKME_LCD_H

#include <Arduino.h>
#include <Wire.h>

class ParkMeLcd {
 public:
  ParkMeLcd(uint8_t address, uint8_t columns, uint8_t rows)
      : address_(address), columns_(columns), rows_(rows), wire_(&Wire) {}

  void begin(TwoWire &wire = Wire) {
    wire_ = &wire;
    wire_->beginTransmission(address_);
    wire_->endTransmission();
    delay(50);

    expanderWrite(backlightMask_);
    delay(1000);

    write4Bits(0x03 << 4);
    delayMicroseconds(4500);
    write4Bits(0x03 << 4);
    delayMicroseconds(4500);
    write4Bits(0x03 << 4);
    delayMicroseconds(150);
    write4Bits(0x02 << 4);

    command(0x28);  // 4-bit mode, 2 lines, 5x8 font
    command(0x08);  // display off
    clear();
    command(0x06);  // entry mode
    command(0x0C);  // display on, cursor off
  }

  void clear() {
    command(0x01);
    delayMicroseconds(2000);
  }

  void home() {
    command(0x02);
    delayMicroseconds(2000);
  }

  void backlight(bool enabled) {
    backlightMask_ = enabled ? 0x08 : 0x00;
    expanderWrite(0);
  }

  void setCursor(uint8_t column, uint8_t row) {
    static const uint8_t rowOffsets[] = {0x00, 0x40, 0x14, 0x54};
    command(0x80 | (column + rowOffsets[row < rows_ ? row : (rows_ - 1)]));
  }

  void printAt(uint8_t row, const String &text) {
    String padded = text;
    while (padded.length() < columns_) {
      padded += ' ';
    }
    padded = padded.substring(0, columns_);

    setCursor(0, row);
    for (uint8_t i = 0; i < padded.length(); ++i) {
      send(static_cast<uint8_t>(padded[i]), 0x01);
    }
  }

 private:
  void command(uint8_t value) { send(value, 0x00); }

  void send(uint8_t value, uint8_t mode) {
    uint8_t highNibble = value & 0xF0;
    uint8_t lowNibble = (value << 4) & 0xF0;
    write4Bits(highNibble | mode);
    write4Bits(lowNibble | mode);
  }

  void write4Bits(uint8_t value) {
    expanderWrite(value);
    pulseEnable(value);
  }

  void expanderWrite(uint8_t value) {
    wire_->beginTransmission(address_);
    wire_->write(value | backlightMask_);
    wire_->endTransmission();
  }

  void pulseEnable(uint8_t value) {
    expanderWrite(value | 0x04);
    delayMicroseconds(1);
    expanderWrite(value & ~0x04);
    delayMicroseconds(50);
  }

  uint8_t address_;
  uint8_t columns_;
  uint8_t rows_;
  uint8_t backlightMask_ = 0x08;
  TwoWire *wire_;
};

#endif
