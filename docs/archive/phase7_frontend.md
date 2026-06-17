We have successfully finalized the backend (FastAPI, PostgreSQL, and Edge Sensor Fusion). My teammate is building the ESP32 hardware.

Now, let's pivot to Phase 4: The Frontend Web Dashboard. 
I plan to deploy this frontend as a static application to Cloudflare Pages. 

Please grill me on the frontend architecture. Ask me 3 sharp, technical questions focusing on:
1. **Real-Time State:** How the UI will efficiently reflect the hardware's continuous heartbeat (e.g., spot occupancy flipping from empty to taken) without overloading the FastAPI server with aggressive polling.
2. **Role-Based Access Control (RBAC):** How we will handle authentication and route protection so a 'student' only sees available spots, but an 'admin' can see the camera logs and violation reports.
3. **Edge Case UI:** How the dashboard will visually handle and alert admins about the "Unidentified Vehicle" state (when the ultrasonic sensor says occupied, but the camera failed to post).

Do not write any HTML/React/Vue code yet. Ask your 3 questions and wait for my architectural solutions.
