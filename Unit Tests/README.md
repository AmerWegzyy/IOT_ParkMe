## This folder contains validation tests done to check sensors/hardware parts

### OLED screen test

File:

```text
Unit Tests/HW_OLED_SSD1306_I2C_Test/HW_OLED_SSD1306_I2C_Test.ino
```

Wiring for ESP32 DevKit:

```text
OLED VCC -> 3V3
OLED GND -> GND
OLED SDA -> GPIO21
OLED SCK -> GPIO22
```

Expected result in Serial Monitor at `115200 baud`:

```text
PASS - OLED I2C address responded
PASS - OLED initialized and WELCOME text displayed
```

Expected result on the OLED:

```text
WELCOME
PARKME
```
