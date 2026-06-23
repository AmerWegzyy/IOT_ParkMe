# ParkMe System Q&A
This document archives important architectural and edge-case Q&A decisions discussed during development.

### Q: Does the LCD show messages like "camera scanning"?
**A:** Yes, the system actually coordinates messages from both the local microcontrollers (instantly) and the backend server. When a vehicle pulls into a spot, the LCD cycles through:
1. **Instant Local Hardware Updates (Via ESP-NOW)**: "Taking photo", "Photo sent", or "Photo failed".
2. **Backend Server Updates (Via Polling)**: "Scanning" (during OCR), "Welcome [Name]", "Access denied", or "Admin review" (if the plate is unreadable).

### Q: When a plate is successfully read but results in a violation, where is the picture saved?
**A:** The picture is saved directly into the `parking_logs` collection. The raw JPEG bytes are Base64 encoded and stored under the `capture_base64` field of the newly created parking log document. It completely bypasses the temporary `spot_captures` collection (which is exclusively used to hold images *while* the Admin is deciding what to do with blurry/unreadable plates).

### Q: In the case of a "Bouncy Driver" (a car leaves within 90 seconds), does the backend delete the encoded picture in the relevant log?
**A:** No, the backend does *not* explicitly wipe the `capture_base64` field. When a driver aborts parking, the backend updates the log by flipping `is_violation` to `False` and changing the `license_plate` to `"ABORTED"`. If the camera managed to upload a picture before the driver aborted, that Base64 string is safely archived in the `parking_logs` document permanently for future auditing purposes (though the frontend automatically hides the "Show Picture" button for aborted logs).

### Q: What happens if the camera's hardware fails completely and never uploads a picture, but the dashboard generates a Ghost Log?
**A:** The frontend explicitly handles this by disabling the "Accept Vehicle" and "Reject Vehicle" buttons. If the image fails to load or hasn't arrived, the Admin is physically blocked from blindly guessing. In this scenario, the Admin physically inspects the spot. When the car is asked to leave, the spot sends a `heartbeat=false`, the spot clears, and the backend proactively wipes the temporary `spot_captures` document to guarantee the missing image state does not accidentally inherit a stale image from a previous car.
