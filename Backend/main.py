import os
from dotenv import load_dotenv
load_dotenv()

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
import firebase_admin
from firebase_admin import credentials, firestore, auth
from google.cloud.firestore_v1 import FieldFilter
from google.cloud import vision
import asyncio
import json

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment Variables
ESP32_HMAC_SECRET = os.environ.get("ESP32_HMAC_SECRET", "super_secret_hmac_key_replace_me_in_production")
FIREBASE_PROJECT_ID = os.environ.get("FIREBASE_PROJECT_ID", "")

# Firebase Setup
# Uses GOOGLE_APPLICATION_CREDENTIALS env var for service account JSON path
if not firebase_admin._apps:
    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred, {"projectId": FIREBASE_PROJECT_ID})

firestore_client = firestore.client()

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
def get_firestore_db():
    """Returns the Firestore client instance."""
    return firestore_client

async def verify_hmac_signature(request: Request):
    """Verifies the HMAC-SHA256 signature to secure the endpoint against spoofing."""
    signature = request.headers.get("X-Signature")
    timestamp = request.headers.get("X-Timestamp")
    
    if not signature or not timestamp:
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
    try:
        client = vision.ImageAnnotatorClient()
        image = vision.Image(content=image_bytes)
        response = client.text_detection(image=image)
        texts = response.text_annotations
        
        if response.error.message:
            logger.error(f"Vision API Error: {response.error.message}")
            return ""
            
        if texts:
            # texts[0] contains the entire text found
            full_text = texts[0].description
            # Extract only digits as the plate number
            plate = "".join(e for e in full_text if e.isdigit())
            return plate
            
    except Exception as e:
        logger.error(f"Failed to extract license plate with Vision API: {str(e)}")
        
    return ""

# ==========================================
# ENDPOINTS
# ==========================================
@app.post("/api/v1/sensors/heartbeat", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(verify_hmac_signature)])
async def receive_heartbeat_data(
    payload: HeartbeatPayload, 
    db = Depends(get_firestore_db)
):
    server_time = get_il_time()
    
    # Find the parking spot by mac_address
    spots_ref = db.collection("parking_spots")
    spot_query = spots_ref.where(filter=FieldFilter("mac_address", "==", payload.mac_address)).limit(1).get()
    
    spot_doc = None
    for doc in spot_query:
        spot_doc = doc
        break
    
    if spot_doc:
        # Update the parking spot
        spot_doc.reference.update({
            "last_seen": server_time,
            "battery_level": payload.battery_level,
            "is_occupied": payload.is_occupied
        })
        
        spot_id = spot_doc.id
        
        # Find active parking log for this spot (no exit_time)
        logs_ref = db.collection("parking_logs")
        active_log_query = (
            logs_ref
            .where(filter=FieldFilter("spot_id", "==", spot_id))
            .where(filter=FieldFilter("exit_time", "==", None))
            .order_by("entry_time", direction=firestore.Query.DESCENDING)
            .limit(1)
            .get()
        )
        
        active_log_doc = None
        for doc in active_log_query:
            active_log_doc = doc
            break
        
        if payload.is_occupied and not active_log_doc:
            # Create a new parking log for unidentified occupancy
            logs_ref.add({
                "spot_id": spot_id,
                "license_plate": "UNIDENTIFIED",
                "entry_time": server_time,
                "exit_time": None,
                "is_violation": True,
                "user_id": None,
                "snapshot_role": None
            })
            
        elif not payload.is_occupied and active_log_doc:
            # Compute time difference in Python instead of SQL strftime
            log_data = active_log_doc.to_dict()
            entry_time = log_data.get("entry_time")
            
            # Handle Firestore timestamp conversion
            if hasattr(entry_time, 'timestamp'):
                # entry_time is a datetime-like object from Firestore
                duration_seconds = (server_time - entry_time.replace(tzinfo=server_time.tzinfo)).total_seconds()
            else:
                duration_seconds = 60  # Default to >= 60 if we can't compute
            
            update_data = {"exit_time": server_time}
            
            if duration_seconds < 60:
                update_data["is_violation"] = False
                update_data["license_plate"] = "ABORTED"
            
            active_log_doc.reference.update(update_data)
        
        # Build updated spot data for SSE broadcast
        spot_data_dict = spot_doc.to_dict()
        spot_data_dict.update({
            "is_occupied": payload.is_occupied,
            "last_seen": server_time,
            "battery_level": payload.battery_level
        })
        
        # Get the current active log for broadcast
        license_plate = None
        is_violation = False
        active_log_query2 = (
            logs_ref
            .where(filter=FieldFilter("spot_id", "==", spot_id))
            .where(filter=FieldFilter("exit_time", "==", None))
            .order_by("entry_time", direction=firestore.Query.DESCENDING)
            .limit(1)
            .get()
        )
        for doc in active_log_query2:
            log_d = doc.to_dict()
            license_plate = log_d.get("license_plate")
            is_violation = log_d.get("is_violation", False)
            break
        
        broadcast_spot = {
            "id": spot_id,
            "category": spot_data_dict.get("category"),
            "is_occupied": payload.is_occupied,
            "license_plate": license_plate,
            "is_violation": is_violation,
            "battery_level": payload.battery_level,
            "last_seen": server_time.isoformat()
        }
        await broadcast_event("spot_update", {"spot": broadcast_spot})

    return {"status": "heartbeat_processed", "timestamp": server_time.isoformat()}


@app.post("/api/v1/sensors/park", status_code=status.HTTP_202_ACCEPTED)
async def receive_park_event(
    spot_id: str = Form(..., description="The parking spot ID this camera monitors"),
    file: UploadFile = File(..., description="Image file from the ESP32-CAM"),
    db = Depends(get_firestore_db)
):
    server_time = get_il_time()
    
    image_bytes = await file.read()
    license_plate = extract_license_plate(image_bytes)
    
    if not license_plate:
        return {
            "status": "failed", 
            "reason": "could_not_read_plate",
            "action": "RETRY",
            "message": "Scan again"
        }
        
    logger.info(f"Extracted plate {license_plate} for spot {spot_id}")
    
    last_seen = LPR_DEDUP_CACHE.get(license_plate)
    if last_seen and (server_time - last_seen).total_seconds() < 5:
        return {
            "status": "dropped", 
            "reason": "duplicate_within_5s",
            "action": "RETRY",
            "message": "Processing..."
        }
    LPR_DEDUP_CACHE[license_plate] = server_time
    
    # Get the parking spot document
    spot_ref = db.collection("parking_spots").document(spot_id)
    spot_doc = spot_ref.get()
    
    if not spot_doc.exists:
        return {
            "status": "failed", 
            "reason": "invalid_spot_id",
            "action": "RETRY",
            "message": "Invalid spot"
        }
        
    spot_data = spot_doc.to_dict()
    spot_category = spot_data.get("category")
    
    # Look up the vehicle by license_plate (document ID = license_plate)
    vehicle_ref = db.collection("vehicles").document(license_plate)
    vehicle_doc = vehicle_ref.get()
    
    vehicle_user = None
    if vehicle_doc.exists:
        vehicle_data = vehicle_doc.to_dict()
        user_id = vehicle_data.get("user_id")
        if user_id:
            # Look up the user
            user_ref = db.collection("users").document(user_id)
            user_doc = user_ref.get()
            if user_doc.exists:
                user_data = user_doc.to_dict()
                vehicle_user = {
                    "user_id": user_id,
                    "name": user_data.get("name"),
                    "role": user_data.get("role")
                }

    is_violation = False
    display_message = ""
    user_id = None
    snapshot_role = None

    if not vehicle_user:
        is_violation = True
        display_message = "access denied"
        logger.warning(f"Unregistered vehicle {license_plate} parked in {spot_id}")
    else:
        user_id = vehicle_user["user_id"]
        snapshot_role = vehicle_user["role"]
        driver_name = vehicle_user["name"]
        
        if snapshot_role == "admin" or snapshot_role == spot_category:
            is_violation = False
            display_message = f"welcome {driver_name}"
        else:
            is_violation = True
            display_message = "access denied"
            logger.warning(f"Role mismatch: {snapshot_role} user {driver_name} parked in {spot_category} spot {spot_id}")

    # Check if there's an active UNIDENTIFIED ghost log created by the heartbeat
    logs_ref = db.collection("parking_logs")
    unidentified_query = (
        logs_ref
        .where(filter=FieldFilter("spot_id", "==", spot_id))
        .where(filter=FieldFilter("license_plate", "==", "UNIDENTIFIED"))
        .where(filter=FieldFilter("exit_time", "==", None))
        .get()
    )
    
    unidentified_doc = None
    for doc in unidentified_query:
        unidentified_doc = doc
        break

    if unidentified_doc:
        # Overwrite the ghost log to clear the Admin UI "Resolve" button
        unidentified_doc.reference.update({
            "license_plate": license_plate,
            "user_id": user_id,
            "snapshot_role": snapshot_role,
            "is_violation": is_violation
            # Keep original entry_time
        })
        logger.info(f"Resolved UNIDENTIFIED ghost log for spot {spot_id} with plate {license_plate}")
    else:
        # Create a new parking log
        logs_ref.add({
            "spot_id": spot_id,
            "license_plate": license_plate,
            "user_id": user_id,
            "snapshot_role": snapshot_role,
            "entry_time": server_time,
            "exit_time": None,
            "is_violation": is_violation
        })
    
    # Update the parking spot
    spot_ref.update({
        "is_occupied": True,
        "last_seen": server_time
    })

    broadcast_spot_data = {
        "id": spot_id,
        "category": spot_category,
        "is_occupied": True,
        "license_plate": license_plate,
        "is_violation": is_violation,
        "battery_level": spot_data.get("battery_level"),
        "last_seen": server_time.isoformat()
    }
    await broadcast_event("spot_update", {"spot": broadcast_spot_data})

    if is_violation:
        await broadcast_event("log_event", {"log": {
            "timestamp": server_time.isoformat(), 
            "type": "unidentified" if not vehicle_user else "violation", 
            "message": f"Violation at Spot {spot_id} by {license_plate}"
        }})

    action = "DENIED" if is_violation else "WELCOME"
    return {
        "status": "park_recorded", 
        "plate": license_plate, 
        "is_violation": is_violation,
        "action": action,
        "message": display_message
    }

def get_current_user(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid auth header")
    token = authorization.split(" ")[1]
    try:
        decoded_token = auth.verify_id_token(token)
        uid = decoded_token.get("uid")
        email = decoded_token.get("email")
        
        # Query Firestore users collection by email to find user name and role
        db = firestore_client
        users_query = db.collection("users").where(filter=FieldFilter("email", "==", email)).limit(1).get()
        user_doc = None
        for doc in users_query:
            user_doc = doc
            break
        
        if user_doc:
            user_data = user_doc.to_dict()
            return {
                "uid": uid,
                "user_id": user_doc.id,
                "email": email,
                "name": user_data.get("name"),
                "role": user_data.get("role"),
                "is_special_needs": user_data.get("role") == "special-needs-driver"
            }
        raise HTTPException(status_code=401, detail="User not found in database")
    except Exception as e:
        logger.error(f"Token verification failed: {str(e)}")
        raise HTTPException(status_code=401, detail="Invalid or expired Firebase token")

@app.get("/api/v1/users/me")
async def get_user_profile(current_user: dict = Depends(get_current_user)):
    return current_user

@app.get("/api/v1/spots")
async def get_all_spots(current_user: dict = Depends(get_current_user), db = Depends(get_firestore_db)):
    # Get all parking spots
    spots_docs = db.collection("parking_spots").get()
    
    # Get all active parking logs (exit_time is None)
    active_logs_query = (
        db.collection("parking_logs")
        .where(filter=FieldFilter("exit_time", "==", None))
        .get()
    )
    
    # Build a lookup: spot_id -> active log data
    active_logs_by_spot = {}
    for log_doc in active_logs_query:
        log_data = log_doc.to_dict()
        log_spot_id = log_data.get("spot_id")
        # Keep the most recent one if multiple exist
        if log_spot_id not in active_logs_by_spot:
            active_logs_by_spot[log_spot_id] = log_data
    
    result = []
    user_role = current_user.get("role")
    
    for spot_doc in spots_docs:
        s = spot_doc.to_dict()
        spot_id = spot_doc.id
        category = s.get("category")
        is_occupied = s.get("is_occupied", False)
        battery_level = s.get("battery_level")
        last_seen = s.get("last_seen")
        
        active_log = active_logs_by_spot.get(spot_id)
        license_plate = active_log.get("license_plate") if active_log else None
        is_violation = active_log.get("is_violation", False) if active_log else False
        
        if user_role == "admin":
            result.append({
                "id": spot_id,
                "category": category,
                "is_occupied": is_occupied,
                "license_plate": license_plate if is_occupied else None,
                "is_violation": is_violation if is_occupied else False,
                "battery_level": battery_level,
                "last_seen": last_seen.isoformat() if hasattr(last_seen, 'isoformat') else str(last_seen) if last_seen else None
            })
        elif category == user_role or (current_user.get("is_special_needs") and category == "special-needs-driver"):
            result.append({
                "id": spot_id,
                "category": category,
                "is_occupied": is_occupied,
                "license_plate": None,
                "is_violation": False
            })
    return {"spots": result}

@app.get("/api/v1/logs")
async def get_recent_logs(current_user: dict = Depends(get_current_user), db = Depends(get_firestore_db)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")
    
    # Firestore doesn't support OR queries across different fields natively,
    # so we run two queries and merge/deduplicate the results.
    logs_ref = db.collection("parking_logs")
    
    # Query 1: is_violation == True
    violation_query = (
        logs_ref
        .where(filter=FieldFilter("is_violation", "==", True))
        .limit(50)
        .get()
    )
    
    # Query 2: license_plate == 'UNIDENTIFIED'
    unidentified_query = (
        logs_ref
        .where(filter=FieldFilter("license_plate", "==", "UNIDENTIFIED"))
        .limit(50)
        .get()
    )
    
    # Merge and deduplicate by document ID
    seen_ids = set()
    all_logs = []
    for doc in list(violation_query) + list(unidentified_query):
        if doc.id not in seen_ids:
            seen_ids.add(doc.id)
            all_logs.append(doc.to_dict())
    
    # Sort by entry_time descending and limit to 50
    all_logs.sort(key=lambda x: x.get("entry_time", datetime.min), reverse=True)
    all_logs = all_logs[:50]
    
    result = []
    for l in all_logs:
        entry_time = l.get("entry_time")
        spot_id = l.get("spot_id")
        license_plate = l.get("license_plate")
        
        msg_type = "unidentified" if license_plate == "UNIDENTIFIED" else "violation"
        msg = f"Camera failure detected at Spot {spot_id}." if msg_type == "unidentified" else f"Unauthorized access at Spot {spot_id} (Plate: {license_plate})"
        result.append({
            "timestamp": entry_time.isoformat() if hasattr(entry_time, 'isoformat') else str(entry_time) if entry_time else None,
            "type": msg_type,
            "message": msg
        })
    return {"logs": result}
@app.get("/api/v1/stream")
async def stream_events(token: str = None):
    if not token:
        raise HTTPException(status_code=401, detail="Missing token")
    try:
        decoded_token = auth.verify_id_token(token)
        uid = decoded_token.get("uid")
        email = decoded_token.get("email")
        
        db = firestore_client
        users_query = db.collection("users").where(filter=FieldFilter("email", "==", email)).limit(1).get()
        user_doc = None
        for doc in users_query:
            user_doc = doc
            break
        
        if not user_doc:
            raise HTTPException(status_code=401, detail="User not found")
        
        user_data = user_doc.to_dict()
        payload = {
            "role": user_data.get("role"),
            "is_special_needs": user_data.get("role") == "special-needs-driver"
        }
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

def get_current_admin(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return current_user

@app.put("/api/v1/sensors/resolve")
async def resolve_spot(payload: ResolvePayload, admin_user: dict = Depends(get_current_admin), db = Depends(get_firestore_db)):
    # Find active logs for this spot with license_plate == 'UNIDENTIFIED'
    logs_ref = db.collection("parking_logs")
    active_logs_query = (
        logs_ref
        .where(filter=FieldFilter("spot_id", "==", payload.spot_id))
        .where(filter=FieldFilter("license_plate", "==", "UNIDENTIFIED"))
        .where(filter=FieldFilter("exit_time", "==", None))
        .get()
    )
    
    for log_doc in active_logs_query:
        log_doc.reference.update({
            "is_violation": False,
            "license_plate": "RESOLVED"
        })
    
    # Get the spot for broadcast
    spot_ref = db.collection("parking_spots").document(payload.spot_id)
    spot_doc = spot_ref.get()
    
    if spot_doc.exists:
        spot_data = spot_doc.to_dict()
        last_seen_raw = spot_data.get("last_seen")
        broadcast_spot_data = {
            "id": spot_doc.id,
            "category": spot_data.get("category"),
            "is_occupied": spot_data.get("is_occupied", False),
            "license_plate": "RESOLVED",
            "is_violation": False,
            "battery_level": spot_data.get("battery_level"),
            "last_seen": last_seen_raw.isoformat() if hasattr(last_seen_raw, 'isoformat') else str(last_seen_raw) if last_seen_raw else None
        }
        await broadcast_event("spot_update", {"spot": broadcast_spot_data})
        await broadcast_event("log_event", {"log": {
            "timestamp": datetime.now().isoformat(), 
            "type": "info", 
            "message": f"Admin {admin_user.get('name')} resolved anomaly at spot {payload.spot_id}."
        }})
        
    return {"status": "resolved", "spot_id": payload.spot_id}

@app.post("/api/v1/telemetry/bulk", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(verify_hmac_signature)])
async def receive_bulk_data(payload: BulkPayload, db = Depends(get_firestore_db)):
    logger.info(f"Received {len(payload.data)} cached events from {payload.mac_address}")
    return {"status": "bulk_processed", "events": len(payload.data)}

import os
frontend_dir = os.path.join(os.path.dirname(__file__), "../Frontend")
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
