Here are my architectural solutions for Phase 2:

1. State Management & Thread Safety:
- ~~[CANCELLED: Replaced by Edge Sensor Fusion] To survive server restarts and crashes, "PENDING" states will be written directly to a lightweight `pending_sessions` database table rather than an in-memory dictionary.~~
- ~~[CANCELLED: Replaced by Edge Sensor Fusion] Upon a server reboot, a startup hook will scan for any lingering "PENDING" entries older than 10 seconds and automatically flag them as a generic "System Processing Timeout" or "Unidentified Vehicle Violation" to maintain data integrity.~~

2. Timestamps & Clock Drift Mitigation:
- We will stamp all incoming payloads with the Server's local time upon receipt instead of trusting the ESP32 internal clock. 
- This eliminates the need to maintain strict NTP synchronization on battery-constrained edge devices and completely mitigates network transmission delay or clock drift errors.

3. LPR Noise & Duplicate Elimination:
- I will implement a backend de-duplication cache: if the exact same license plate is read by the same camera within a 5-second sliding window, subsequent payloads are dropped as noise.
- To avoid background vehicle false-positives, an LPR payload will only be linked to a spot transaction if that specific parking spot's ultrasonic sensor registers an active transition change within the matching time frame.
