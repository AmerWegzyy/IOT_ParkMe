import os
import hmac
import hashlib
import logging
from datetime import datetime, timedelta
import zoneinfo
from typing import List

def get_il_time():
    return datetime.now(zoneinfo.ZoneInfo("Asia/Jerusalem"))

from fastapi import FastAPI, BackgroundTasks, Depends, HTTPException, status, Request, UploadFile, File, Form, Header
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
import cv2
import numpy as np
import pytesseract
import jwt
import asyncio
import json

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment Variables
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./parkme.db")
ESP32_HMAC_SECRET = os.environ.get("ESP32_HMAC_SECRET", "super_secret_hmac_key_replace_me_in_production")
JWT_SECRET = os.environ.get("JWT_SECRET", "super_secret_jwt_key_replace_me_in_production")
JWT_ALGORITHM = "HS256"

# Database Setup
engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=10, max_overflow=20)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

app = FastAPI(title="ParkMe API", description="IoT Backend for Smart Parking System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# SSE Broadcaster
sse_clients = []

async def broadcast_event(event_type: str, data: dict):
    message = json.dumps({"type": event_type, **data})
    for client in sse_clients:
        if client["role"] == "admin":
            await client["queue"].put(message)
        elif event_type == "spot_update":
            spot_cat = data.get("spot", {}).get("category")
            if spot_cat == client["role"] or (client.get("is_special_needs") and spot_cat == "special-needs-driver"):
                await client["queue"].put(message)
        # Log events are only pushed to admins

# ==========================================
# PYDANTIC SCHEMAS
# ==========================================
class HeartbeatPayload(BaseModel):
    mac_address: str = Field(..., description="MAC Address of the ESP32 node")
    is_occupied: bool = Field(..., description="Current physical occupancy state")
    battery_level: float = Field(..., ge=0, le=100, description="Battery percentage")

# LPRPayload is removed since we now use Form data and File uploads for LPR

class BulkTelemetryItem(BaseModel):
    t: int = Field(..., description="Unix timestamp of the event")
    v: bool = Field(..., description="Occupancy value")

class BulkPayload(BaseModel):
    mac_address: str
    data: List[BulkTelemetryItem]

class LoginPayload(BaseModel):
    email: str
    password: str

class ResolvePayload(BaseModel):
    spot_id: str

# In-memory deduplication cache for LPR reads. Maps: license_plate -> datetime
LPR_DEDUP_CACHE = {}

# ==========================================
# DEPENDENCIES & MIDDLEWARE
# ==========================================
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

async def verify_hmac_signature(request: Request):
    """Verifies the HMAC-SHA256 signature to secure the endpoint against spoofing."""
    signature = request.headers.get("X-Signature")
    timestamp = request.headers.get("X-Timestamp")
    
    if not signature or not timestamp:
        # Relaxed for development, uncomment for production
        # raise HTTPException(status_code=401, detail="Missing HMAC signature or timestamp")
        return
        
    req_time = datetime.fromtimestamp(int(timestamp))
    if datetime.now() - req_time > timedelta(seconds=30):
        raise HTTPException(status_code=401, detail="Request expired (Replay attack detected)")

    body = await request.body()
    message = f"{timestamp}.{body.decode('utf-8')}".encode('utf-8')
    expected_mac = hmac.new(ESP32_HMAC_SECRET.encode('utf-8'), message, hashlib.sha256).hexdigest()
    
    if not hmac.compare_digest(expected_mac, signature):
        raise HTTPException(status_code=401, detail="Invalid HMAC signature")

# ==========================================
# LPR PROCESSING (SERVER-SIDE)
# ==========================================
def extract_license_plate(image_bytes: bytes) -> str:
    """Extracts license plate string from image bytes using OpenCV and Tesseract."""
    # 1. Convert bytes to numpy array
    np_arr = np.frombuffer(image_bytes, np.uint8)
    # 2. Decode image
    img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    if img is None:
        logger.error("Failed to decode image bytes")
        return ""
        
    # Crop the image sides slightly to remove the blue 'IL' sidebars
    h, w = img.shape[:2]
    crop_margin = int(w * 0.05)  # Crop 5% off both sides
    img = img[:, crop_margin:w-crop_margin]
    
    # Scale up the image (Tesseract needs characters to be at least 30px high)
    img = cv2.resize(img, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    
    # 3. Preprocess image for OCR (Grayscale, blur, threshold)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5,5), 0)
    _, thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    
    # 4. Run Tesseract OCR (config forces ONLY digits for Israeli plates)
    custom_config = r'--oem 3 --psm 7 -c tessedit_char_whitelist=0123456789'
    text_extracted = pytesseract.image_to_string(thresh, config=custom_config)
    
    # Clean up extracted text
    plate = "".join(e for e in text_extracted if e.isdigit())
    return plate

# ==========================================
# ENDPOINTS
# ==========================================
@app.post("/api/v1/sensors/heartbeat", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(verify_hmac_signature)])
async def receive_heartbeat_data(
    payload: HeartbeatPayload, 
    db: Session = Depends(get_db)
):
    server_time = get_il_time()
    
    # Always update the hardware telemetry
    db.execute(
        text("UPDATE parking_spots SET last_seen = :now, battery_level = :batt, is_occupied = :occ WHERE mac_address = :mac"),
        {"now": server_time, "batt": payload.battery_level, "occ": payload.is_occupied, "mac": payload.mac_address}
    )
    db.commit()
    
    # State-Sync Logic
    spot = db.execute(text("SELECT id FROM parking_spots WHERE mac_address = :mac"), {"mac": payload.mac_address}).fetchone()
    if spot:
        # Find the currently active session (no exit_time)
        active_log = db.execute(
            text("SELECT id, entry_time FROM parking_logs WHERE spot_id = :spot_id AND exit_time IS NULL ORDER BY entry_time DESC LIMIT 1"),
            {"spot_id": spot.id}
        ).fetchone()
        
        if payload.is_occupied and not active_log:
            # 2. "Broken Camera" Recovery: Spot is physically occupied, but no camera POST arrived.
            db.execute(
                text("INSERT INTO parking_logs (spot_id, license_plate, entry_time, is_violation) VALUES (:spot_id, 'UNIDENTIFIED', :now, TRUE)"),
                {"spot_id": spot.id, "now": server_time}
            )
            db.commit()
            
        elif not payload.is_occupied and active_log:
            # 1. Vehicle Departure: State transitioned to False.
            # 3. Bouncing Driver: If departure is < 60 seconds from arrival, flag as ABORTED.
            db.execute(
                text("""
                UPDATE parking_logs 
                SET exit_time = :now, 
                    is_violation = CASE 
                        WHEN (strftime('%s', :now) - strftime('%s', entry_time)) < 60 THEN FALSE 
                        ELSE is_violation 
                    END,
                    license_plate = CASE
                        WHEN (strftime('%s', :now) - strftime('%s', entry_time)) < 60 THEN 'ABORTED'
                        ELSE license_plate
                    END
                WHERE id = :id
                """),
                {"now": server_time, "id": active_log.id}
            )
            db.commit()
    # Fetch updated spot state to broadcast
    if spot:
        updated_spot = db.execute(
            text("""
                SELECT p.id, p.category, p.is_occupied, l.license_plate, l.is_violation
                FROM parking_spots p
                LEFT JOIN parking_logs l ON l.spot_id = p.id AND l.exit_time IS NULL
                WHERE p.id = :spot_id
            """),
            {"spot_id": spot.id}
        ).fetchone()
        if updated_spot:
            spot_data = {
                "id": updated_spot[0],
                "category": updated_spot[1],
                "is_occupied": updated_spot[2],
                "license_plate": updated_spot[3],
                "is_violation": updated_spot[4]
            }
            await broadcast_event("spot_update", {"spot": spot_data})

    return {"status": "heartbeat_processed", "timestamp": server_time.isoformat()}


@app.post("/api/v1/sensors/park", status_code=status.HTTP_202_ACCEPTED)
async def receive_park_event(
    spot_id: str = Form(..., description="The parking spot ID this camera monitors"),
    file: UploadFile = File(..., description="Image file from the ESP32-CAM"),
    db: Session = Depends(get_db)
):
    """
    Edge Sensor Fusion: Receives the camera image on arrival and creates the transaction.
    """
    server_time = get_il_time()
    
    image_bytes = await file.read()
    license_plate = extract_license_plate(image_bytes)
    
    if not license_plate:
        return {"status": "failed", "reason": "could_not_read_plate"}
        
    logger.info(f"Extracted plate {license_plate} for spot {spot_id}")
    
    # Deduplication (5-second window)
    last_seen = LPR_DEDUP_CACHE.get(license_plate)
    if last_seen and (server_time - last_seen).total_seconds() < 5:
        return {"status": "dropped", "reason": "duplicate_within_5s"}
    LPR_DEDUP_CACHE[license_plate] = server_time
    
    # Single-Post Logic: Identify spot rules and vehicle owner
    spot = db.execute(
        text("SELECT category FROM parking_spots WHERE id = :spot_id"),
        {"spot_id": spot_id}
    ).fetchone()
    
    if not spot:
        return {"status": "failed", "reason": "invalid_spot_id"}
        
    spot_category = spot.category
    
    # Look up the vehicle and user
    vehicle_user = db.execute(
        text("""
            SELECT u.id as user_id, u.name, u.role 
            FROM vehicles v 
            JOIN users u ON v.user_id = u.id 
            WHERE v.license_plate = :plate
        """),
        {"plate": license_plate}
    ).fetchone()

    is_violation = False
    display_message = ""
    user_id = None
    snapshot_role = None

    if not vehicle_user:
        # Unregistered vehicle
        is_violation = True
        display_message = "access denied"
        logger.warning(f"Unregistered vehicle {license_plate} parked in {spot_id}")
    else:
        user_id = vehicle_user.user_id
        snapshot_role = vehicle_user.role
        driver_name = vehicle_user.name
        
        # Rule: Admin can park anywhere. Otherwise, user role must match spot category.
        if snapshot_role == "admin" or snapshot_role == spot_category:
            is_violation = False
            display_message = f"welcome {driver_name}"
        else:
            is_violation = True
            display_message = "access denied"
            logger.warning(f"Role mismatch: {snapshot_role} user {driver_name} parked in {spot_category} spot {spot_id}")

    # Create transaction and mark spot as occupied instantly
    db.execute(
        text("""
            INSERT INTO parking_logs (spot_id, license_plate, user_id, snapshot_role, entry_time, is_violation) 
            VALUES (:spot_id, :plate, :user_id, :role, :now, :is_violation)
        """),
        {
            "spot_id": spot_id, 
            "plate": license_plate, 
            "user_id": user_id, 
            "role": snapshot_role,
            "now": server_time,
            "is_violation": is_violation
        }
    )
    db.execute(
        text("UPDATE parking_spots SET is_occupied = TRUE, last_seen = :now WHERE id = :spot_id"),
        {"spot_id": spot_id, "now": server_time}
    )
    db.commit()

    spot_data = {
        "id": spot_id,
        "category": spot_category,
        "is_occupied": True,
        "license_plate": license_plate,
        "is_violation": is_violation
    }
    await broadcast_event("spot_update", {"spot": spot_data})

    if is_violation:
        await broadcast_event("log_event", {"log": {
            "timestamp": server_time.isoformat(), 
            "type": "unidentified" if not vehicle_user else "violation", 
            "message": f"Violation at Spot {spot_id} by {license_plate}"
        }})

    return {
        "status": "park_recorded", 
        "plate": license_plate, 
        "is_violation": is_violation,
        "display_message": display_message
    }

def get_current_user(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid auth header")
    token = authorization.split(" ")[1]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

@app.get("/api/v1/spots")
async def get_all_spots(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    spots = db.execute(text("""
        SELECT p.id, p.category, p.is_occupied, l.license_plate, l.is_violation, p.battery_level, p.last_seen
        FROM parking_spots p
        LEFT JOIN parking_logs l ON l.spot_id = p.id AND l.exit_time IS NULL
    """)).fetchall()
    
    result = []
    user_role = current_user.get("role")
    
    for s in spots:
        if user_role == "admin":
            result.append({
                "id": s[0],
                "category": s[1],
                "is_occupied": s[2],
                "license_plate": s[3] if s[2] else None,
                "is_violation": s[4] if s[2] else False,
                "battery_level": s[5],
                "last_seen": s[6].isoformat() if hasattr(s[6], 'isoformat') else str(s[6]) if s[6] else None
            })
        elif s[1] == user_role or (current_user.get("is_special_needs") and s[1] == "special-needs-driver"):
            result.append({
                "id": s[0],
                "category": s[1],
                "is_occupied": s[2],
                "license_plate": None,
                "is_violation": False
            })
    return {"spots": result}

@app.get("/api/v1/logs")
async def get_recent_logs(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")
    logs = db.execute(text("""
        SELECT entry_time, spot_id, license_plate, is_violation, exit_time
        FROM parking_logs
        WHERE is_violation = TRUE OR license_plate = 'UNIDENTIFIED'
        ORDER BY entry_time DESC LIMIT 50
    """)).fetchall()
    
    result = []
    for l in logs:
        msg_type = "unidentified" if l[2] == 'UNIDENTIFIED' else "violation"
        msg = f"Camera failure detected at Spot {l[1]}." if msg_type == "unidentified" else f"Unauthorized access at Spot {l[1]} (Plate: {l[2]})"
        result.append({
            "timestamp": l[0].isoformat() if hasattr(l[0], 'isoformat') else str(l[0]) if l[0] else None,
            "type": msg_type,
            "message": msg
        })
    return {"logs": result}
@app.post("/api/v1/auth/login")
async def login(payload: LoginPayload, db: Session = Depends(get_db)):
    user = db.execute(text("SELECT id, name, email, role FROM users WHERE email = :email"), {"email": payload.email}).fetchone()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    token_payload = {
        "sub": user.email,
        "name": user.name,
        "role": user.role,
        "is_special_needs": user.role == "special-needs-driver",
        "exp": datetime.utcnow() + timedelta(days=1)
    }
    token = jwt.encode(token_payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return {"access_token": token, "token_type": "bearer"}

@app.get("/api/v1/stream")
async def stream_events(token: str = None):
    if not token:
        raise HTTPException(status_code=401, detail="Missing token")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    q = asyncio.Queue()
    client = {"queue": q, "role": payload.get("role"), "is_special_needs": payload.get("is_special_needs", False)}
    sse_clients.append(client)

    async def event_generator():
        try:
            while True:
                message = await q.get()
                yield f"data: {message}\n\n"
        except asyncio.CancelledError:
            sse_clients.remove(client)
            raise

    return StreamingResponse(event_generator(), media_type="text/event-stream")

def get_current_admin(authorization: str = Header(...)):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid auth header")
    token = authorization.split(" ")[1]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Admin privileges required")
        return payload
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

@app.put("/api/v1/sensors/resolve")
async def resolve_spot(payload: ResolvePayload, admin_user: dict = Depends(get_current_admin), db: Session = Depends(get_db)):
    db.execute(
        text("""
            UPDATE parking_logs 
            SET is_violation = FALSE, license_plate = 'RESOLVED'
            WHERE spot_id = :spot_id AND license_plate = 'UNIDENTIFIED' AND exit_time IS NULL
        """),
        {"spot_id": payload.spot_id}
    )
    db.commit()
    
    spot = db.execute(text("SELECT id, category, is_occupied FROM parking_spots WHERE id = :spot_id"), {"spot_id": payload.spot_id}).fetchone()
    if spot:
        spot_data = {
            "id": spot[0],
            "category": spot[1],
            "is_occupied": spot[2],
            "license_plate": "RESOLVED",
            "is_violation": False
        }
        await broadcast_event("spot_update", {"spot": spot_data})
        await broadcast_event("log_event", {"log": {
            "timestamp": datetime.now().isoformat(), 
            "type": "info", 
            "message": f"Admin {admin_user.get('name')} resolved anomaly at spot {payload.spot_id}."
        }})
        
    return {"status": "resolved", "spot_id": payload.spot_id}

@app.post("/api/v1/telemetry/bulk", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(verify_hmac_signature)])
async def receive_bulk_data(payload: BulkPayload, db: Session = Depends(get_db)):
    logger.info(f"Received {len(payload.data)} cached events from {payload.mac_address}")
    return {"status": "bulk_processed", "events": len(payload.data)}

import os
frontend_dir = os.path.join(os.path.dirname(__file__), "../Frontend")
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
