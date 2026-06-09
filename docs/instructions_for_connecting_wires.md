# ParkMe Hardware Connection & Flashing Guide

This guide contains everything you need to wire and flash the two distinct nodes in the ParkMe system. Follow these instructions carefully to ensure a perfect first-time setup.

---

## 1. Parking Spot Sensor Node (Regular ESP32)

This node is placed at individual parking spots. It uses an ultrasonic sensor to monitor physical occupancy.

### Required Hardware
- 1x ESP32 Development Board (e.g., NodeMCU ESP32-WROOM)
- 1x HC-SR04 Ultrasonic Sensor
- 2x Resistors for voltage divider (e.g., 1kΩ and 2kΩ)

### Wiring Diagram
| Component | Pin | ESP32 Pin | Notes |
| :--- | :--- | :--- | :--- |
| **Ultrasonic** | `VCC` | `5V` / `VIN` | The HC-SR04 requires 5V to operate reliably. |
| **Ultrasonic** | `GND` | `GND` | Connect to a common ground rail. |
| **Ultrasonic** | `TRIG` | `GPIO 5` | Direct connection. |
| **Ultrasonic** | `ECHO` | `GPIO 18` | **⚠️ CRITICAL**: The HC-SR04 outputs a 5V signal, but the ESP32 GPIOs are 3.3V tolerant. To prevent frying the board, use a voltage divider: `ECHO` ➜ `1kΩ resistor` ➜ `GPIO 18` ➜ `2kΩ resistor` ➜ `GND`. |
| **Battery (Opt)**| `V+` | `GPIO 34` | Needs a 2.0 ratio voltage divider to step down the battery voltage safely. |
| **Calibration** | `Button`| `GPIO 0` | You can use the built-in `BOOT` button on the ESP32 board for calibration. No wiring needed! |

### Firmware Upload
1. Open the Arduino IDE.
2. Navigate to the `ESP32/ParkMeSensorNode` directory and open `ParkMeSensorNode.ino`.
3. Copy `ESP32/SECRETS.example.h` to a new file named `ESP32/SECRETS.h`. Fill in your local Wi-Fi credentials and backend URLs.
4. Select **ESP32 Dev Module** from the Boards menu.
5. Connect via USB and click **Upload**.

---

## 2. Gate Node (ESP32-CAM)

This node is placed at the entrance gate. It takes pictures of license plates and displays server instructions on an LCD.

### Required Hardware
- 1x AI-Thinker ESP32-CAM Module
- 1x FTDI Programmer (USB-to-TTL Serial Adapter)
- 1x HC-SR04 Ultrasonic Sensor
- 1x 16x2 I2C LCD Display Screen
- 2x Resistors for voltage divider (e.g., 1kΩ and 2kΩ)

### Wiring Diagram
| Component | Pin | ESP32-CAM Pin | Notes |
| :--- | :--- | :--- | :--- |
| **Ultrasonic** | `VCC` | `5V` | Ensure stable 5V power. |
| **Ultrasonic** | `GND` | `GND` | |
| **Ultrasonic** | `TRIG` | `GPIO 12` | Direct connection. |
| **Ultrasonic** | `ECHO` | `GPIO 13` | **⚠️ CRITICAL**: Add a voltage divider (5V to 3.3V) exactly as described in the Sensor Node section above. |
| **I2C LCD** | `VCC` | `5V` | Most 16x2 I2C LCDs require 5V. |
| **I2C LCD** | `GND` | `GND` | |
| **I2C LCD** | `SDA` | `GPIO 14` | Direct connection. |
| **I2C LCD** | `SCL` | `GPIO 15` | Direct connection. |

### Firmware Upload
*Note: The ESP32-CAM does not have a built-in USB port. You must use an FTDI programmer.*

1. Connect the FTDI programmer to the ESP32-CAM:
   - `5V` ➜ `5V`
   - `GND` ➜ `GND`
   - `U0R` ➜ `U0T` (TX)
   - `U0T` ➜ `U0R` (RX)
2. **Put ESP32-CAM in Flash Mode**: Connect `GPIO 0` to `GND` using a jumper wire.
3. Plug the FTDI programmer into your computer.
4. Open the `ESP32/ParkMeCameraNode` directory and open `ParkMeCameraNode.ino`.
5. Ensure `SECRETS.h` is filled out.
6. Select **AI Thinker ESP32-CAM** from the Boards menu and click **Upload**.
7. **After Uploading**: Disconnect the `GPIO 0` jumper wire and press the tiny `RST` (Reset) button on the back of the ESP32-CAM.

---

## 🏆 Final Checklist for "First Time" Success
1. **Common Ground**: Ensure all sensors, the LCD, and the ESP32 modules share the exact same GND line.
2. **Protect the 3.3V Pins**: Do not skip the voltage divider on the HC-SR04 `ECHO` pins. The ESP32 pins will burn out over time if exposed to 5V directly.
3. **I2C LCD Address**: The codebase assumes the LCD's I2C address is `0x27`. If the screen lights up but only shows blank square blocks, its address might be `0x3F`. Change `PARKME_GATE_LCD_ADDRESS` in `SECRETS.h` if necessary.
4. **Stable Power Supply**: The ESP32-CAM requires a stable 5V supply with at least 1A of current. Using a weak laptop USB port might cause the camera to "brownout" and continuously restart whenever it tries to turn on the WiFi or the flash LED.
