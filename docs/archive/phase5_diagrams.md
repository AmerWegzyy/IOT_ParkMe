My teammate and I need visual documentation for our project. Since I am using a CLI, please generate the diagrams using **Mermaid.js syntax** so I can paste them into an online viewer.

Please provide two separate Mermaid code blocks:

1. **Entity Relationship Diagram (ERD):**
   - Use the `erDiagram` syntax.
   - Map out the exact relationships between the `users`, `vehicles`, `parking_spots`, and `parking_logs` tables based on our SQLite/PostgreSQL schema.
   - Include the primary and foreign keys.

2. **Sequence/Architecture Diagram:**
   - Use the `sequenceDiagram` syntax.
   - ~~[CANCELLED: Replaced by Edge Sensor Fusion Single POST & Heartbeat] Show the exact flow of communication between the ESP32 Ultrasonic Node, the ESP32-CAM (LPR), and the FastAPI Server.~~
   - Draw arrows for the HTTP POST requests.
   - IMPORTANT: Add a `Note over` or `Note right of` the arrows that explicitly shows the exact JSON or Multipart expected payload for each event.
