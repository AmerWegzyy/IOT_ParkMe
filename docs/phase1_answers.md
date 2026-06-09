Here are my architectural solutions for Phase 1:

1. Relational Integrity & History:
- To allow multiple vehicles while protecting integrity, the vehicles table will use a Foreign Key pointing to user_id without a UNIQUE constraint (making it One-to-Many).
- To prevent role updates from corrupting history, the parking_logs table will store a denormalized text snapshot of the driver's role ('student', 'faculty') at the exact timestamp of entry.

2. Telemetry State & Bloat Prevention:
- The parking_spots table will act as a live state machine. Sensors will perform an UPDATE query to refresh 'last_seen' and 'battery_level' in-place, keeping table rows constant.
- The 'Offline' status will not be stored. It will be computed programmatically by the server: if (CURRENT_TIMESTAMP - last_seen) exceeds a 5-minute threshold, the system flags the node as offline.

3. Asynchronous Event Synchronization:
- ~~[CANCELLED: Replaced by Edge Sensor Fusion] I will implement a sliding time-window join on the FastAPI server layer. When an ultrasonic sensor registers occupancy, it initiates a parking transaction row with 'license_plate = PENDING'.~~
- ~~[CANCELLED: Replaced by Edge Sensor Fusion] The server will listen for incoming LPR camera payloads within a sliding window of +/- 10 seconds. If a plate is received within that threshold, it updates the pending transaction. If the timer expires with no plate associated, an automatic violation log is triggered.~~
