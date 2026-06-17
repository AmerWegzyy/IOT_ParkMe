Here are my solutions to the Edge Sensor Fusion edge cases:

1. Vehicle Departure (State Sync Heartbeat):
The ESP32-CAM will only fire on arrival. The ESP32 Microcontroller's heartbeat ping will be upgraded to include the physical state (`is_occupied: bool`). When the FastAPI server receives a heartbeat where the state transitions from True to False, the server will query the active session for that spot and stamp the `exit_time`, returning the spot to available status.

2. "Broken Camera" State Recovery:
The ESP32 Microcontroller's heartbeat serves as the absolute "Ground Truth." If the server receives a heartbeat indicating `is_occupied = True`, but no active parking log exists (due to camera failure or network drop), the server will automatically create a fallback parking log with `license_plate = 'UNIDENTIFIED'`. This ensures the spot is marked as unavailable on the dashboard and flags the spot for a manual security check.

3. The "Bouncing" Driver (Grace Period Logic):
I will implement a brief Grace Period (e.g., 60 seconds) in the backend. If a vehicle arrives, triggers the camera POST, but the server subsequently receives an `is_occupied = False` heartbeat within that 60-second window, the server will close the log with a status of 'ABORTED_PARKING'. This self-corrects the phantom parking event without penalizing the driver.
