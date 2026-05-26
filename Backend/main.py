from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import hashlib
from pydantic import BaseModel

# ==========================================
# 1. SERVER INITIALIZATION & CLOUD CONFIG
# ==========================================
app = FastAPI(title="ParkMe API Gateway - Technion Server")

# CORS Setup: Allows your index.html file to communicate securely with this server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"],
)

DB_FILE = "parkme.db"

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

# ==========================================
# 2. DATA SCHEMAS
# ==========================================
class LoginRequest(BaseModel):
    username: str
    password: str

class SpotUpdateRequest(BaseModel):
    spot_id: int
    status: int          # 0 = Free, 1 = Occupied
    battery_level: float

# ==========================================
# 3. WEB DASHBOARD API ENDPOINTS
# ==========================================
@app.post("/api/login")
def login_user(data: LoginRequest):
    """Verifies credentials coming from the index.html website."""
    conn = get_db_connection()
    user = conn.execute(
        "SELECT * FROM users WHERE username = ? AND password_hash = ?",
        (data.username, hash_password(data.password))
    ).fetchone()
    conn.close()
    
    if user:
        return {
            "status": "success",
            "user_id": user["user_id"],
            "name": user["name"],
            "role": user["user_type"],
            "is_looking": bool(user["is_looking"])
        }
    raise HTTPException(status_code=401, detail="Invalid credentials")

@app.get("/api/live-map")
def get_live_map():
    """Returns the current state of all parking nodes for the frontend grid."""
    conn = get_db_connection()
    spots = conn.execute("SELECT spot_id, spot_type, status, battery_level, last_seen FROM parking_spots").fetchall()
    conn.close()
    return [dict(spot) for spot in spots]

@app.get("/api/logs")
def get_security_logs():
    """Returns the historical incident table for the Admin Security view."""
    conn = get_db_connection()
    logs = conn.execute("SELECT * FROM parking_logs ORDER BY timestamp DESC").fetchall()
    conn.close()
    return [dict(log) for log in logs]

# ==========================================
# 4. ESP32 HARDWARE API ENDPOINTS
# ==========================================
@app.post("/api/update-spot")
def update_spot_telemetry(data: SpotUpdateRequest):
    """
    Receives raw sensor pings from the ESP32 Ultrasonic Nodes.
    Updates DB and auto-generates EXIT logs when a spot clears.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Update physical spot metrics
    cursor.execute("""
        UPDATE parking_spots 
        SET status = ?, battery_level = ?, last_seen = CURRENT_TIMESTAMP 
        WHERE spot_id = ?
    """, (data.status, data.battery_level, data.spot_id))
    
    # If a car just left (Status 0), log the exit
    if data.status == 0:
        cursor.execute(
            "INSERT INTO parking_logs (spot_id, action) VALUES (?, 'EXIT')", 
            (data.spot_id,)
        )
        print(f"[SYSTEM ALERTER] Spot {data.spot_id} freed! Triggering client-side network search routines...")
    
    conn.commit()
    conn.close()
    return {"status": "telemetry_updated"}

@app.post("/api/gate-entry")
async def process_gate_entry(spot_id: int = Form(...), photo: UploadFile = File(...)):
    """
    Receives image bytes from ESP32-CAM, processes them via AI, 
    verifies permissions, and replies directly to the hardware.
    """
    # Import isolated AI module
    from analyze_photo import extract_license_plate
    
    image_bytes = await photo.read()
    
    # 1. OCR Extraction Phase
    detected_plate = extract_license_plate(image_bytes)
    print(f"[GATE AI] Processing gateway node. Extracted Plate: '{detected_plate}'")
    
    if not detected_plate:
        return {"action": "DENIED", "message": "Cannot read plate"}
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 2. Database Identity Match Phase
    vehicle = conn.execute("""
        SELECT v.license_plate, u.name, u.user_type 
        FROM vehicles v 
        JOIN users u ON v.user_id = u.user_id 
        WHERE v.license_plate = ?
    """, (detected_plate,)).fetchone()
    
    spot = conn.execute("SELECT spot_type FROM parking_spots WHERE spot_id = ?", (spot_id,)).fetchone()
    
    # 3. Security Check: Unregistered Vehicle
    if not vehicle:
        cursor.execute(
            "INSERT INTO parking_logs (spot_id, license_plate, action) VALUES (?, ?, 'VIOLATION_ATTEMPT')",
            (spot_id, detected_plate)
        )
        conn.commit()
        conn.close()
        return {"action": "DENIED", "message": "Unknown vehicle"}
        
    # 4. Privilege Clearance Check (Mapping DB tiers)
    required_type = spot["spot_type"] if spot else None
    user_role = vehicle["user_type"]
    
    # Helper to map the string accurately
    mapped_role = "special needs" if user_role == "special needs driver" else user_role

    # Admins bypass the check; everyone else must match the spot type
    if required_type and mapped_role != required_type and user_role != "admin":
        cursor.execute(
            "INSERT INTO parking_logs (spot_id, license_plate, action) VALUES (?, ?, 'VIOLATION_ATTEMPT')",
            (spot_id, detected_plate)
        )
        conn.commit()
        conn.close()
        return {"action": "DENIED", "message": "Access Denied"}
        
    # 5. Success Phase: Log Authorized Entry & Open Gate
    cursor.execute(
        "INSERT INTO parking_logs (spot_id, license_plate, action) VALUES (?, ?, 'ENTRY')",
        (spot_id, detected_plate)
    )
    conn.commit()
    conn.close()
    
    return {"action": "WELCOME", "message": f"Welcome {vehicle['name']}"}