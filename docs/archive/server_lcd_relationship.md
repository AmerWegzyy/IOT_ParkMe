# ParkMe — Server and LCD Relationship

This document details the communication flow between the FastAPI Server and the ESP32 Camera/Gate Node, specifically focusing on how server responses dictate what the driver sees on the Gate's 16x2 I2C LCD screen.

---

## 1. The Communication Protocol

When a vehicle approaches the gate, the ESP32 Camera Node takes a photo and sends it to the server (`POST /api/v1/sensors/park`). The server processes the image (OCR and Registration checks) and returns a JSON payload.

To trigger the LCD properly, the Server guarantees the presence of two key fields in the JSON response:
*   `"action"`: Determines the high-level logic the gate should follow (`"WELCOME"`, `"DENIED"`, or `"RETRY"`).
*   `"message"`: The specific string to display on the second line of the LCD screen (maximum 16 characters).

---

## 2. Server Actions & LCD Display States

Depending on the `action` field returned by the server, the ESP32 Camera Node executes specific LCD screen updates and hardware behaviors.

### Action: `WELCOME`
*   **Trigger:** The backend successfully reads the plate, finds the user in the database, and confirms the user has the correct role (e.g. Admin, or matches the Spot category).
*   **Backend JSON Example:**
    ```json
    {
      "status": "park_recorded",
      "plate": "1234567",
      "is_violation": false,
      "action": "WELCOME",
      "message": "welcome Alice"
    }
    ```
*   **LCD Display:**
    *   **Line 1:** `Access granted  `
    *   **Line 2:** `welcome Alice   `
*   **Hardware Event:** The gate relay is pulsed (opens the physical barrier), and the screen pauses for 2.5 seconds before asking the driver to clear the gate.

### Action: `DENIED`
*   **Trigger:** The backend successfully reads the plate, but the vehicle is either completely unregistered or has a role mismatch (e.g. Student parked in Special Needs).
*   **Backend JSON Example:**
    ```json
    {
      "status": "park_recorded",
      "plate": "7654321",
      "is_violation": true,
      "action": "DENIED",
      "message": "access denied"
    }
    ```
*   **LCD Display:**
    *   **Line 1:** `Access denied   `
    *   **Line 2:** `access denied   `
*   **Hardware Event:** The gate relay is **not** pulsed. The screen pauses for 2.5 seconds, then asks the driver to clear the gate without granting entry.

### Action: `RETRY`
*   **Trigger:** The server encounters a temporary failure preventing it from identifying the vehicle. Examples:
    *   **OCR Failure:** The camera image was too blurry or dark, so no text was extracted. (Message: `"Scan again"`)
    *   **Invalid Spot:** The Gate's configured spot ID does not exist in the database. (Message: `"Invalid spot"`)
    *   **Duplicate Scan:** The camera accidentally fired twice within 5 seconds. (Message: `"Processing..."`)
*   **Backend JSON Example (OCR Failure):**
    ```json
    {
      "status": "failed",
      "reason": "could_not_read_plate",
      "action": "RETRY",
      "message": "Scan again"
    }
    ```
*   **LCD Display:**
    *   **Line 1:** `Scan again      `
    *   **Line 2:** `(or message)    `
*   **Hardware Event:** The ESP32 waits 2 seconds, and then enters the **Retry Loop**.

---

## 3. The Auto-Retry Loop

If the ESP32 encounters a `RETRY` action (or an `UNKNOWN` action due to a server crash), it attempts to automatically recover.

1.  **Retry Prompt:** It updates the LCD to show its retry progress:
    *   **Line 1:** `Retrying...     `
    *   **Line 2:** `1/3             ` (Updates to 2/3, then 3/3).
2.  **Delay & Re-Scan:** It delays for 1 second, then snaps a brand new photo. The screen displays `"Capturing... / Hold still"`.
3.  **Loop Limit:** It will repeat this up to **3 times**.
    *   If any of the retries return a `WELCOME` or `DENIED`, the loop breaks immediately and finalizes the driver's entry/rejection.
    *   If all 3 retries result in failure, the system gives up to prevent an infinite loop holding up traffic.

---

## 4. Standby & Clearing States

When the system is idle or has finished interacting with a driver, it uses these two states:

*   **Waiting for Car (Idle):**
    *   **Line 1:** `Ready to scan   `
    *   **Line 2:** `Approach gate   `
    *   *Triggered when the ultrasonic sensor detects no vehicle.*
*   **Finished / Stuck (Lockout):**
    *   **Line 1:** `Please          `
    *   **Line 2:** `Clear gate      `
    *   *Triggered after a successful `WELCOME`/`DENIED` action, or after failing all 3 retries. The screen locks on this message until the physical car drives away from the ultrasonic sensor's range.*
