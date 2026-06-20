import os
from dotenv import load_dotenv
load_dotenv()

import logging
from datetime import datetime, timedelta
import zoneinfo
from pathlib import Path
from typing import List, Optional
import uuid


def _resolve_il_timezone():
    for timezone_name in ("Asia/Jerusalem", "Israel"):
        try:
            return zoneinfo.ZoneInfo(timezone_name)
        except zoneinfo.ZoneInfoNotFoundError:
            continue
    return None


IL_TIMEZONE = _resolve_il_timezone()


def get_il_time():
    if IL_TIMEZONE is not None:
        return datetime.now(IL_TIMEZONE)

    # Windows dev machines may not have IANA tzdata installed yet.
    return datetime.now().astimezone()

from fastapi import FastAPI, BackgroundTasks, Depends, HTTPException, status, UploadFile, File, Form, Header
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
from cachetools import TTLCache

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

backend_dir = Path(__file__).resolve().parent
for env_filename in (".env", "env"):
    env_path = backend_dir / env_filename
    if env_path.exists():
        load_dotenv(env_path)
        break

# Environment Variables
FIREBASE_PROJECT_ID = os.environ.get("FIREBASE_PROJECT_ID", "")
FIREBASE_CLOCK_SKEW_SECONDS = int(os.environ.get("FIREBASE_CLOCK_SKEW_SECONDS", "10"))
ENVIRONMENT = os.environ.get("ENVIRONMENT", "development").lower()

# Firebase Setup
# Uses GOOGLE_APPLICATION_CREDENTIALS locally and Cloud Run ADC in production.
if not firebase_admin._apps:
    cred = credentials.ApplicationDefault()
    firebase_options = {"projectId": FIREBASE_PROJECT_ID} if FIREBASE_PROJECT_ID else {}
    firebase_admin.initialize_app(cred, firebase_options)

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
CAMERA_COMMANDS_COLLECTION = "camera_commands"
CAMERA_COMMAND_STALE_SECONDS = 90

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

class ResolvePayload(BaseModel):
    spot_id: str


class CameraPollPayload(BaseModel):
    camera_mac: str = Field(..., description="MAC address reported by the ESP32-CAM")


class CameraCommandResultPayload(BaseModel):
    camera_mac: str
    request_id: str
    status: str = Field(..., description="COMPLETED or FAILED")
    detail: Optional[str] = None


class DebugCameraTriggerPayload(BaseModel):
    spot_id: Optional[str] = None
    camera_mac: Optional[str] = None
    reason: str = "manual_trigger"

# In-memory deduplication cache for LPR reads. Maps: license_plate -> datetime
# TTL of 120s covers the ~45s camera retry window with margin, and is well
# below the 6-minute heartbeat interval so it won't interfere with other timing.
LPR_DEDUP_CACHE = TTLCache(maxsize=1000, ttl=120)

# ==========================================
# DEPENDENCIES & MIDDLEWARE
# ==========================================
def get_firestore_db():
    """Returns the Firestore client instance."""
    return firestore_client

def get_latest_active_log_for_spot(logs_ref, spot_id: str):
    """Returns the newest active parking log for a spot without requiring a Firestore composite index."""
    active_logs = (
        logs_ref
        .where(filter=FieldFilter("spot_id", "==", spot_id))
        .where(filter=FieldFilter("exit_time", "==", None))
        .get()
    )

    latest_doc = None
    latest_entry_timestamp = float("-inf")
    for doc in active_logs:
        entry_time = doc.to_dict().get("entry_time")
        entry_timestamp = entry_time.timestamp() if hasattr(entry_time, "timestamp") else float("-inf")
        if entry_timestamp > latest_entry_timestamp:
            latest_doc = doc
            latest_entry_timestamp = entry_timestamp

    return latest_doc


def find_spot_by_mac(spots_ref, mac_address: str, *field_names: str):
    """Find the first parking spot whose configured MAC matches any provided field name."""
    candidates = []
    for candidate in (mac_address.strip(), mac_address.strip().upper(), mac_address.strip().lower()):
        if candidate and candidate not in candidates:
            candidates.append(candidate)

    for field_name in field_names:
        for candidate in candidates:
            query = spots_ref.where(filter=FieldFilter(field_name, "==", candidate)).limit(1).get()
            for doc in query:
                return doc
    return None


def normalize_mac(mac_address: str) -> str:
    return mac_address.strip().upper()


def get_camera_command_ref(db, camera_mac: str):
    return db.collection(CAMERA_COMMANDS_COLLECTION).document(normalize_mac(camera_mac))


def get_command_reference_time(command_data: dict):
    return command_data.get("claimed_at") or command_data.get("queued_at")


def is_stale_command(command_data: dict, now: datetime, stale_after_seconds: int = CAMERA_COMMAND_STALE_SECONDS):
    reference_time = get_command_reference_time(command_data)
    if not hasattr(reference_time, "timestamp"):
        return True
    return (now - reference_time.replace(tzinfo=now.tzinfo)).total_seconds() > stale_after_seconds


def queue_capture_command(db, camera_mac: str, spot_id: str, reason: str):
    normalized_mac = normalize_mac(camera_mac)
    command_ref = get_camera_command_ref(db, normalized_mac)
    existing_doc = command_ref.get()
    now = get_il_time()

    if existing_doc.exists:
        existing_data = existing_doc.to_dict() or {}
        if existing_data.get("status") in {"PENDING", "CLAIMED"} and not is_stale_command(existing_data, now):
            return existing_data

    request_id = str(uuid.uuid4())
    command_data = {
        "request_id": request_id,
        "action": "CAPTURE",
        "status": "PENDING",
        "camera_mac": normalized_mac,
        "spot_id": spot_id,
        "reason": reason,
        "queued_at": now
    }
    command_ref.set(command_data)
    return command_data


def claim_capture_command(db, camera_mac: str):
    command_ref = get_camera_command_ref(db, camera_mac)
    command_doc = command_ref.get()

    if not command_doc.exists:
        return None

    command_data = command_doc.to_dict() or {}
    if command_data.get("status") != "PENDING":
        return None

    claimed_at = get_il_time()
    command_ref.update({
        "status": "CLAIMED",
        "claimed_at": claimed_at
    })
    command_data["status"] = "CLAIMED"
    command_data["claimed_at"] = claimed_at
    return command_data


def complete_capture_command(db, camera_mac: str, request_id: str, status_text: str, detail: str | None):
    command_ref = get_camera_command_ref(db, camera_mac)
    command_doc = command_ref.get()

    if not command_doc.exists:
        return False

    command_data = command_doc.to_dict() or {}
    if command_data.get("request_id") != request_id:
        return False

    command_ref.update({
        "status": status_text.upper(),
        "detail": detail,
        "completed_at": get_il_time()
    })
    return True

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
            logger.info(f"[DEBUG] Vision API detected raw text:\n{full_text}")
            
            # Extract only digits as the plate number
            plate = "".join(e for e in full_text if e.isdigit())
            logger.info(f"[DEBUG] Extracted digits (plate): '{plate}'")
            return plate
        else:
            logger.warning("[DEBUG] Vision API returned a successful response, but found NO text in the image.")
            
    except Exception as e:
        logger.error(f"[DEBUG] Failed to extract license plate with Vision API (Likely a credentials/network issue): {str(e)}")
        
    return ""


def build_gate_response(action: str,
                        status_text: str,
                        message: str,
                        *,
                        plate: str | None = None,
                        is_violation: bool | None = None,
                        reason: str | None = None) -> dict:
    response = {
        "action": action,
        "status": status_text,
        "message": message,
        "display_message": message
    }
    if plate is not None:
        response["plate"] = plate
    if is_violation is not None:
        response["is_violation"] = is_violation
    if reason is not None:
        response["reason"] = reason
    return response

# ==========================================
# ENDPOINTS
# ==========================================
@app.post("/api/v1/sensors/heartbeat", status_code=status.HTTP_202_ACCEPTED)
async def receive_heartbeat_data(
    payload: HeartbeatPayload, 
    db = Depends(get_firestore_db)
):
    server_time = get_il_time()
    
    # Support both the new sensor_mac schema and the older mac_address field.
    spots_ref = db.collection("parking_spots")
    spot_doc = find_spot_by_mac(spots_ref, payload.mac_address, "sensor_mac", "mac_address")
    
    if spot_doc:
        spot_data_before = spot_doc.to_dict()
        previous_is_occupied = bool(spot_data_before.get("is_occupied", False))
        camera_mac = spot_data_before.get("camera_mac") or spot_data_before.get("mac_address")
        spot_id = spot_doc.id

        # Find active parking log for this spot (no exit_time)
        logs_ref = db.collection("parking_logs")
        active_log_doc = get_latest_active_log_for_spot(logs_ref, spot_id)
        is_new_arrival = payload.is_occupied and not previous_is_occupied
        should_queue_camera = False

        if payload.is_occupied:
            # If the spot was previously free but an active log still exists,
            # treat it as stale state and close it before starting a fresh cycle.
            if is_new_arrival and active_log_doc:
                logger.warning(
                    "Closing stale active log for spot %s before processing a new arrival.",
                    spot_id
                )
                active_log_doc.reference.update({"exit_time": server_time})
                active_log_doc = None

            # Create the ghost log on a real FREE -> OCCUPIED transition, or
            # self-heal if occupancy is true but the active log is missing.
            if is_new_arrival or not active_log_doc:
                logs_ref.add({
                    "spot_id": spot_id,
                    "license_plate": "UNIDENTIFIED",
                    "entry_time": server_time,
                    "exit_time": None,
                    "is_violation": True,
                    "user_id": None,
                    "snapshot_role": None
                })
                should_queue_camera = True
            elif payload.is_occupied and active_log_doc:
                logger.info(
                    "Spot %s remains occupied with an active log; skipping duplicate camera queue.",
                    spot_id
                )

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

        # Update the parking spot
        spot_doc.reference.update({
            "last_seen": server_time,
            "battery_level": payload.battery_level,
            "is_occupied": payload.is_occupied
        })

        if should_queue_camera and camera_mac:
            queue_capture_command(db, camera_mac, spot_id, "occupancy_detected")
            logger.info(
                "Queued camera capture for spot %s (camera %s) after FREE -> OCCUPIED.",
                spot_id,
                camera_mac
            )
        
        # Build updated spot data for SSE broadcast
        spot_data_dict = spot_data_before
        spot_data_dict.update({
            "is_occupied": payload.is_occupied,
            "last_seen": server_time,
            "battery_level": payload.battery_level
        })
        
        # Get the current active log for broadcast
        license_plate = None
        is_violation = False
        latest_active_log_doc = get_latest_active_log_for_spot(logs_ref, spot_id)
        if latest_active_log_doc:
            log_d = latest_active_log_doc.to_dict()
            license_plate = log_d.get("license_plate")
            is_violation = log_d.get("is_violation", False)
        
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


@app.post("/api/v1/cameras/poll")
async def poll_camera_command(payload: CameraPollPayload, db = Depends(get_firestore_db)):
    command_data = claim_capture_command(db, payload.camera_mac)
    if not command_data:
        return {"action": "IDLE"}

    queued_at = command_data.get("queued_at")
    claimed_at = command_data.get("claimed_at")
    return {
        "action": command_data.get("action", "IDLE"),
        "request_id": command_data.get("request_id"),
        "spot_id": command_data.get("spot_id"),
        "reason": command_data.get("reason"),
        "queued_at": queued_at.isoformat() if hasattr(queued_at, "isoformat") else str(queued_at) if queued_at else None,
        "claimed_at": claimed_at.isoformat() if hasattr(claimed_at, "isoformat") else str(claimed_at) if claimed_at else None
    }


@app.post("/api/v1/cameras/result")
async def complete_camera_command(payload: CameraCommandResultPayload, db = Depends(get_firestore_db)):
    success = complete_capture_command(
        db,
        payload.camera_mac,
        payload.request_id,
        payload.status,
        payload.detail
    )
    if not success:
        raise HTTPException(status_code=404, detail="Matching camera command not found")

    return {"status": "acknowledged", "request_id": payload.request_id}


@app.post("/api/v1/debug/cameras/trigger")
async def debug_trigger_camera(payload: DebugCameraTriggerPayload, db = Depends(get_firestore_db)):
    if ENVIRONMENT != "development":
        raise HTTPException(status_code=403, detail="Debug camera trigger is disabled outside development")

    camera_mac = payload.camera_mac
    spot_id = payload.spot_id

    if spot_id:
        spot_doc = db.collection("parking_spots").document(spot_id).get()
        if not spot_doc.exists:
            raise HTTPException(status_code=404, detail="Spot not found")
        spot_data = spot_doc.to_dict() or {}
        camera_mac = camera_mac or spot_data.get("camera_mac") or spot_data.get("mac_address")
        spot_id = spot_doc.id

    if not camera_mac:
        raise HTTPException(status_code=400, detail="Provide spot_id or camera_mac")

    normalized_camera_mac = normalize_mac(camera_mac)
    if not spot_id:
        spots_ref = db.collection("parking_spots")
        spot_doc = find_spot_by_mac(spots_ref, normalized_camera_mac, "camera_mac", "mac_address")
        if not spot_doc:
            raise HTTPException(status_code=404, detail="No parking spot found for that camera MAC")
        spot_id = spot_doc.id

    command_data = queue_capture_command(db, normalized_camera_mac, spot_id, payload.reason)
    queued_at = command_data.get("queued_at")
    return {
        "status": command_data.get("status"),
        "action": command_data.get("action"),
        "request_id": command_data.get("request_id"),
        "spot_id": command_data.get("spot_id"),
        "camera_mac": command_data.get("camera_mac"),
        "reason": command_data.get("reason"),
        "queued_at": queued_at.isoformat() if hasattr(queued_at, "isoformat") else str(queued_at) if queued_at else None
    }


@app.post("/api/v1/sensors/park", status_code=status.HTTP_202_ACCEPTED)
async def receive_park_event(
    camera_mac: str = Form(..., description="The MAC address of the camera node"),
    file: UploadFile = File(..., description="Image file from the ESP32-CAM"),
    db = Depends(get_firestore_db)
):
    server_time = get_il_time()
    
    image_bytes = await file.read()
    license_plate = extract_license_plate(image_bytes)
    
    if not license_plate:
        return build_gate_response("RETRY",
                                   "failed",
                                   "scan again",
                                   reason="could_not_read_plate")
        
    logger.info(f"Extracted plate {license_plate} from camera {camera_mac}")

    last_seen = LPR_DEDUP_CACHE.get(license_plate)
    if last_seen and (server_time - last_seen).total_seconds() < 5:
        return build_gate_response("RETRY",
                                   "dropped",
                                   "retry shortly",
                                   plate=license_plate,
                                   reason="duplicate_within_5s")
    LPR_DEDUP_CACHE[license_plate] = server_time
    
    # Support both the new camera_mac schema and the older mac_address field.
    spots_ref = db.collection("parking_spots")
    spot_doc = find_spot_by_mac(spots_ref, camera_mac, "camera_mac", "mac_address")

    if not spot_doc:
        return build_gate_response("RETRY",
                                   "failed",
                                   "invalid camera",
                                   reason="invalid_camera_mac")
        
    spot_id = spot_doc.id
    spot_data = spot_doc.to_dict()
    spot_category = spot_data.get("category")
    spot_ref = spot_doc.reference
    
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
    return build_gate_response(action,
                               "park_recorded",
                               display_message,
                               plate=license_plate,
                               is_violation=is_violation)

def get_current_user(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid auth header")
    token = authorization.split(" ")[1]
    try:
        decoded_token = auth.verify_id_token(token, clock_skew_seconds=FIREBASE_CLOCK_SKEW_SECONDS)
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
    
    logs_ref = db.collection("parking_logs")
    
    # Fetch all logs, ordered natively by Firestore
    recent_logs_query = (
        logs_ref
        .order_by("entry_time", direction=firestore.Query.DESCENDING)
        .limit(50)
        .get()
    )
    
    result = []
    for doc in recent_logs_query:
        l = doc.to_dict()
        entry_time = l.get("entry_time")
        spot_id = l.get("spot_id")
        license_plate = l.get("license_plate")
        is_violation = l.get("is_violation", False)
        
        if license_plate == "UNIDENTIFIED":
            msg_type = "unidentified"
            msg = f"Camera failure detected at Spot {spot_id}."
        elif license_plate == "RESOLVED":
            msg_type = "info"
            msg = f"Admin resolved anomaly at Spot {spot_id}."
        elif license_plate == "ABORTED":
            msg_type = "info"
            msg = f"Driver aborted parking at Spot {spot_id}."
        elif is_violation:
            msg_type = "violation"
            msg = f"Unauthorized access at Spot {spot_id} (Plate: {license_plate})"
        else:
            # Intentional: The Security Log only shows anomalies (violations,
            # unidentified, resolved, aborted). Normal authorized parking
            # events are excluded by design.
            continue
            
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
        decoded_token = auth.verify_id_token(token, clock_skew_seconds=FIREBASE_CLOCK_SKEW_SECONDS)
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
        finally:
            sse_clients.remove(client)

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
            "timestamp": get_il_time().isoformat(), 
            "type": "info", 
            "message": f"Admin {admin_user.get('name')} resolved anomaly at spot {payload.spot_id}."
        }})
        
    return {"status": "resolved", "spot_id": payload.spot_id}

@app.post("/api/v1/telemetry/bulk", status_code=status.HTTP_202_ACCEPTED)
async def receive_bulk_data(payload: BulkPayload, db = Depends(get_firestore_db)):
    logger.info(f"Received {len(payload.data)} cached events from {payload.mac_address}")
    
    # Support both the new sensor_mac schema and the older mac_address field.
    spots_ref = db.collection("parking_spots")
    spot_doc = find_spot_by_mac(spots_ref, payload.mac_address, "sensor_mac", "mac_address")
        
    if not spot_doc:
        logger.warning(f"Bulk data received for unknown MAC: {payload.mac_address}")
        return {"status": "failed", "reason": "unknown_mac"}
        
    spot_id = spot_doc.id
    logs_ref = db.collection("parking_logs")
    
    events = sorted(payload.data, key=lambda x: x.t)
    
    for item in events:
        event_time = datetime.fromtimestamp(item.t, tz=IL_TIMEZONE) if IL_TIMEZONE else datetime.fromtimestamp(item.t).astimezone()
        is_occupied = item.v
        
        # Get current active log
        active_log_doc = get_latest_active_log_for_spot(logs_ref, spot_id)
            
        if is_occupied and not active_log_doc:
            logs_ref.add({
                "spot_id": spot_id,
                "license_plate": "UNIDENTIFIED",
                "entry_time": event_time,
                "exit_time": None,
                "is_violation": True,
                "user_id": None,
                "snapshot_role": None
            })
        elif not is_occupied and active_log_doc:
            log_data = active_log_doc.to_dict()
            entry_time = log_data.get("entry_time")
            
            if hasattr(entry_time, 'timestamp'):
                duration_seconds = (event_time - entry_time.replace(tzinfo=event_time.tzinfo)).total_seconds()
            else:
                duration_seconds = 60
                
            update_data = {"exit_time": event_time}
            if duration_seconds < 60:
                update_data["is_violation"] = False
                update_data["license_plate"] = "ABORTED"
                
            active_log_doc.reference.update(update_data)
            
    if events:
        last_event = events[-1]
        spot_doc.reference.update({
            "is_occupied": last_event.v,
            "last_seen": get_il_time()
        })
        
        # Build updated spot data for SSE broadcast
        spot_data_dict = spot_doc.to_dict()
        spot_data_dict.update({
            "is_occupied": last_event.v,
            "last_seen": get_il_time()
        })
        
        license_plate = None
        is_violation = False
        latest_active_log_doc = get_latest_active_log_for_spot(logs_ref, spot_id)
        if latest_active_log_doc:
            log_d = latest_active_log_doc.to_dict()
            license_plate = log_d.get("license_plate")
            is_violation = log_d.get("is_violation", False)
        
        broadcast_spot = {
            "id": spot_id,
            "category": spot_data_dict.get("category"),
            "is_occupied": last_event.v,
            "license_plate": license_plate,
            "is_violation": is_violation,
            "battery_level": spot_data_dict.get("battery_level"),
            "last_seen": get_il_time().isoformat()
        }
        await broadcast_event("spot_update", {"spot": broadcast_spot})

    return {"status": "bulk_processed", "events": len(payload.data)}

frontend_dir = os.path.join(os.path.dirname(__file__), "../Frontend")
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
