Here are my architectural solutions for Phase 3:

1. PostgreSQL Migration & Concurrency:
- We will route FastAPI database connections through Supabase's built-in PgBouncer pooler using transaction mode, configuring SQLAlchemy connection pools to match server limits.
- To prevent Lost Update anomalies when the LPR and Ultrasonic endpoints are hit simultaneously, we will implement Pessimistic Locking using SQLAlchemy's `.with_for_update()`. This locks the targeted log row immediately, forcing the subsequent query to wait until the active transaction commits.

2. IoT Edge Security:
- Device tokens/keys will be provisioned directly into the ESP32's protected NVS (Non-Volatile Storage) partition rather than being hardcoded in plain-text code.
- To secure traffic efficiently, the ESP32 will use its hardware-accelerated crypto engine to generate an HMAC-SHA256 signature combining the payload and a timestamp. FastAPI middleware will recompute this hash and enforce a strict 30-second freshness window to reject replay attacks without heavy TLS handshakes.

3. API Contracts & Payload Optimization:
- FastAPI's native Swagger documentation (`/docs`) will serve as the living API contract for my teammate, defining explicit Pydantic models.
- For offline caching, a dedicated bulk upload endpoint (`/api/v1/telemetry/bulk`) will accept a flat JSON array optimized with minimal, short object keys (e.g., `{"t": timestamp, "v": value}`) to prevent string allocation overhead on the ESP32. The backend will parse this collection and perform a single-transaction bulk insert.
