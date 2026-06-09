# Phase 8: Final System Architecture

This document visualizes the complete, production-ready architecture of the ParkMe system, reflecting all the pivots and upgrades we implemented (Edge Sensor Fusion, Server-Sent Events, JWT Role-Based Access Control, and the Vanilla JS Dashboard).

```mermaid
flowchart TD
    %% Entities
    Vehicle(fa:fa-car Vehicle)
    
    %% Hardware Node
    subgraph ESP32["ESP32-CAM Node (Edge)"]
        Sensor[Ultrasonic Sensor]
        Camera[OV2640 Camera]
        MCU[ESP32 Processing]
    end

    %% Edge Logic
    Vehicle -- Arrives/Departs --> Sensor
    Sensor -- State Change --> MCU
    MCU -- Wakes up --> Camera
    Camera -- Captures Image --> MCU
    
    %% Backend
    subgraph FastAPI["FastAPI Backend (Cloudflare Pages Ready)"]
        Auth[JWT Auth Middleware]
        HeartbeatAPI["POST /sensors/heartbeat"]
        ParkAPI["POST /sensors/park"]
        StreamAPI["GET /stream (SSE)"]
        ResolveAPI["PUT /sensors/resolve"]
        LPR[Tesseract OCR Engine]
        DB[(SQLite parkme.db)]
        SSE[Asyncio Event Queues]
    end
    
    %% Network Comm
    MCU -- "Periodic State (Occupancy/Battery)" --> HeartbeatAPI
    MCU -- "Image + Spot ID (Form Data)" --> ParkAPI
    
    %% Backend Internal
    ParkAPI -- "Extracts License Plate" --> LPR
    LPR -- "Validates vs Allowed Roles" --> DB
    HeartbeatAPI -- "Detects 'Broken Camera' Anomaly" --> DB
    ParkAPI -- "Logs Entry/Exit/Violations" --> DB
    
    HeartbeatAPI -- "Triggers State Update" --> SSE
    ParkAPI -- "Triggers Log/Spot Update" --> SSE
    ResolveAPI -- "Clears Anomaly" --> DB
    ResolveAPI -- "Broadcasts Resolution" --> SSE
    
    %% Frontend Clients
    subgraph Frontend["Vanilla JS Dashboard"]
        DriverUI["Driver View (Role-Filtered)"]
        AdminUI["Admin View (Telemetry + Logs)"]
    end
    
    %% Client Comm
    Auth -- "Validates Token" --> StreamAPI
    SSE -- "Pushes Real-Time JSON" --> StreamAPI
    StreamAPI -. "Persistent SSE Connection" .-> DriverUI
    StreamAPI -. "Persistent SSE Connection" .-> AdminUI
    AdminUI -- "Acknowledge Alert" --> ResolveAPI
    
    %% Styling
    classDef hardware fill:#2d3436,color:#dfe6e9,stroke:#00b894,stroke-width:2px
    classDef backend fill:#0984e3,color:#fff,stroke:#74b9ff,stroke-width:2px
    classDef database fill:#e17055,color:#fff,stroke:#fab1a0,stroke-width:2px
    classDef frontend fill:#6c5ce7,color:#fff,stroke:#a29bfe,stroke-width:2px
    
    class ESP32,Sensor,Camera,MCU hardware
    class FastAPI,Auth,HeartbeatAPI,ParkAPI,StreamAPI,ResolveAPI,LPR,SSE backend
    class DB database
    class Frontend,DriverUI,AdminUI frontend
```

### Key Architectural Highlights
1. **Edge Sensor Fusion**: The ESP32 acts as the authoritative source of truth. It manages the camera wake-cycle locally, drastically reducing network overhead.
2. **"Broken Camera" Healing**: The `/sensors/heartbeat` endpoint actively cross-references the physical occupancy state against the OCR logs. If a car is physically present but the camera failed to capture a plate, the backend automatically flags it as `UNIDENTIFIED`.
3. **SSE Broadcaster**: Instead of the frontend polling the database, the FastAPI backend maintains an array of `asyncio` queues. Database modifications instantly trigger an `await broadcast_event`, piping the JSON down the active HTTP streams.
4. **Strict RBAC**: The `/stream` and `/spots` endpoints cryptographically verify the JWT. Standard drivers are mathematically shielded from receiving JSON payloads belonging to administrative or mismatched spots.
