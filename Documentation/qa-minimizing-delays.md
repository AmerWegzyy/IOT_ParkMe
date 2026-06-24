# Q&A: Minimizing Delays and Transitioning from Polling to SSE

This document summarizes the design decisions made during the `/grill-me` interview regarding the transition from HTTP polling to Server-Sent Events (SSE) and FreeRTOS dual-core task splitting to minimize display delays.

## 1. Threading and Core Assignment
**Question:** How should we prevent network I/O from blocking the display and sensor readings?
**Answer:** Use FreeRTOS tasks. We will run network I/O operations (WiFi maintenance, SSE stream reading, telemetry HTTP POSTs) on Core 0. We will keep the sensor sampling and display rendering (OLED) on Core 1 (the main loop). This ensures the display remains responsive even if a network request hangs.

## 2. Inter-Core Communication
**Question:** How will Core 0 and Core 1 communicate safely?
**Answer:** We will use shared volatile structs protected by a FreeRTOS mutex. Core 0 will write new display commands to a shared struct, and Core 1 will read them and render them to the OLED.

## 3. Communication Protocol
**Question:** Which protocol should we use to replace polling that works through firewalls and proxies with low latency?
**Answer:** Server-Sent Events (SSE). It is a standard HTTP GET request that keeps the connection open, allowing the server to push data (one-way server-to-ESP32) instantly. It works over standard HTTP/HTTPS ports (80/443).

## 4. Backend Implementation
**Question:** How should the backend handle display commands?
**Answer:** 
- Create a dedicated `/api/v1/displays/stream` SSE endpoint for hardware displays.
- The backend pushes display commands directly via the SSE stream when `queue_display_command()` is called.
- Stop writing to Firestore entirely for display commands — they are ephemeral and writing them to the database adds unnecessary latency. Instead, use an in-memory dictionary.
- Identification: Use `display_id` (e.g., `display-c1`) as a query parameter in the SSE connection.
- Keep-alive: The server must send SSE comment pings (`: keepalive\n\n`) every 15 seconds to prevent firewalls from dropping the connection.

## 5. Acknowledgment
**Question:** How does the server know the display successfully rendered the command?
**Answer:** The ESP32 should send a lightweight HTTP POST acknowledgment to `/api/v1/displays/result` after rendering. This must be sent from the background network task (Core 0) to avoid blocking the main loop.

## 6. Fallback Mechanism
**Question:** What happens if the SSE connection drops or fails to connect?
**Answer:** Fall back to HTTP polling at the current 750ms interval. For reconnecting to the SSE stream, use an exponential backoff strategy (starting at 3 seconds and capping at 30 seconds) to avoid spamming the server.

## 7. Sensor Sampling
**Question:** Should we reduce the ultrasonic sensor sampling count to speed up the loop?
**Answer:** No, keep the current 3 samples (120ms each) to maintain measurement robustness. The dual-core split already eliminates the network delays, so reducing the sample count is unnecessary.

## 8. Scope of Changes
**Question:** Does this dual-core split apply to all ESP32 nodes?
**Answer:** No, the dual-core split applies *only* to the `ParkMeSensorNode`. Other nodes (like the camera or gateway) do not require this change at the moment.
