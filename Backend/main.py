import os
from dotenv import load_dotenv
load_dotenv()

import logging
from collections import Counter
from datetime import datetime, timedelta
import zoneinfo
from pathlib import Path
from typing import List, Optional
import uuid
import base64


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
from fastapi.responses import StreamingResponse, Response
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

try:
    from parking_logic import should_preserve_recent_active_log, seconds_since
except ImportError:
    from Backend.parking_logic import should_preserve_recent_active_log, seconds_since

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
DISPLAY_COMMANDS_COLLECTION = "display_commands"
BOUNCY_DRIVER_MAX_SECONDS = 90
LPR_DEDUP_CACHE_TTL_SECONDS = 120
CAMERA_FIRST_HEARTBEAT_GRACE_SECONDS = 10
CAMERA_UPLOAD_GRACE_SECONDS = 30
DISPLAY_SCANNING_HOLD_MS = 3000
DISPLAY_MANUAL_REVIEW_HOLD_MS = 8000
DISPLAY_WELCOME_HOLD_MS = 5000
DISPLAY_REJECT_HOLD_MS = 25000
DISPLAY_SPOT_CLEARED_HOLD_MS = 1500
UNIDENTIFIED_PLATE = "UNIDENTIFIED"
RESOLVED_PLATE = "RESOLVED"
REJECTED_PLATE = "REJECTED"
MANUAL_ACCEPTED_PLATE = "MANUAL_ACCEPTED"

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


class DisplayPollPayload(BaseModel):
    display_id: str = Field(..., description="Logical display node identifier")


class DisplayCommandResultPayload(BaseModel):
    display_id: str
    request_id: str
    status: str = Field(..., description="DISPLAYED or FAILED")
    detail: Optional[str] = None

# In-memory deduplication cache for LPR reads. Maps: license_plate -> datetime
# TTL of 120s covers short-lived repeat scans with enough margin to avoid
# duplicate reads while still expiring well before heartbeat-driven state ages out.
LPR_DEDUP_CACHE = TTLCache(maxsize=1000, ttl=LPR_DEDUP_CACHE_TTL_SECONDS)

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


def save_review_capture_for_spot(spot_id: str, image_bytes: bytes):
    safe_spot_id = "".join(
        ch for ch in spot_id.strip().lower() if ch.isalnum() or ch in {"-", "_"}
    ) or "spot"
    
    db = firestore_client
    db.collection("spot_captures").document(safe_spot_id).set({
        "image_base64": base64.b64encode(image_bytes).decode("utf-8"),
        "updated_at": get_il_time()
    })
    
    captured_at = get_il_time().isoformat()
    return {
        "review_capture_path": f"/api/v1/captures/{safe_spot_id}",
        "review_capture_at": captured_at
    }

@app.get("/api/v1/captures/{spot_id}")
async def get_capture(spot_id: str, db = Depends(get_firestore_db)):
    safe_spot_id = "".join(
        ch for ch in spot_id.strip().lower() if ch.isalnum() or ch in {"-", "_"}
    ) or "spot"
    doc = db.collection("spot_captures").document(safe_spot_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Capture not found")
    data = doc.to_dict()
    image_base64 = data.get("image_base64")
    if not image_base64:
        raise HTTPException(status_code=404, detail="Capture data missing")
    
    image_bytes = base64.b64decode(image_base64)
    return Response(content=image_bytes, media_type="image/jpeg")


@app.get("/api/v1/logs/{log_id}/capture")
async def get_log_capture(log_id: str, db = Depends(get_firestore_db)):
    doc = db.collection("parking_logs").document(log_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Log not found")
    data = doc.to_dict()
    capture_base64 = data.get("capture_base64")
    if not capture_base64:
        raise HTTPException(status_code=404, detail="No capture associated with this log")
    
    image_bytes = base64.b64decode(capture_base64)
    return Response(content=image_bytes, media_type="image/jpeg")


def build_review_capture_url(spot_data: dict):
    capture_path = spot_data.get("review_capture_path")
    if not capture_path:
        return None
    capture_at = spot_data.get("review_capture_at")
    return f"{capture_path}?v={capture_at}" if capture_at else capture_path


def timestamp_to_iso(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value) if value is not None else None


def clear_review_capture_fields():
    return {
        "review_capture_path": firestore.DELETE_FIELD,
        "review_capture_at": firestore.DELETE_FIELD
    }


def clear_review_metadata_fields():
    return {
        "review_started_at": firestore.DELETE_FIELD,
        "review_resolve_after": firestore.DELETE_FIELD,
        "review_status": firestore.DELETE_FIELD
    }


def clear_review_flow_fields():
    cleared_fields = clear_review_capture_fields()
    cleared_fields.update(clear_review_metadata_fields())
    return cleared_fields


def build_review_deadline(review_started_at):
    if not hasattr(review_started_at, "tzinfo"):
        return None
    return review_started_at + timedelta(seconds=CAMERA_UPLOAD_GRACE_SECONDS)


def get_review_status(license_plate: str | None, spot_data: dict, now: datetime):
    if license_plate != UNIDENTIFIED_PLATE:
        return None, None

    review_capture_url = build_review_capture_url(spot_data)
    review_resolve_after = spot_data.get("review_resolve_after")
    if review_resolve_after is None:
        review_started_at = spot_data.get("review_started_at")
        if review_started_at is not None:
            review_resolve_after = build_review_deadline(review_started_at)

    if review_capture_url:
        return "photo_review", timestamp_to_iso(review_resolve_after)

    if review_resolve_after is not None:
        overdue_seconds = seconds_since(review_resolve_after, now)
        if overdue_seconds is not None and overdue_seconds >= 0:
            return "missing_photo", timestamp_to_iso(review_resolve_after)

    return "awaiting_capture", timestamp_to_iso(review_resolve_after)


def build_effective_spot_state(is_occupied: bool,
                               license_plate: str | None,
                               is_violation: bool,
                               review_capture_url: str | None = None,
                               review_status: str | None = None,
                               review_resolve_after: str | None = None):
    effective = {
        "is_occupied": is_occupied,
        "license_plate": license_plate,
        "is_violation": is_violation,
        "review_capture_url": review_capture_url,
        "review_status": review_status,
        "review_resolve_after": review_resolve_after
    }

    if license_plate == RESOLVED_PLATE:
        effective["is_occupied"] = False
        effective["license_plate"] = None
        effective["is_violation"] = False
        effective["review_capture_url"] = None
        effective["review_status"] = None
        effective["review_resolve_after"] = None
    elif license_plate == MANUAL_ACCEPTED_PLATE:
        effective["is_occupied"] = True
        effective["is_violation"] = False
        effective["review_capture_url"] = None
        effective["review_status"] = None
        effective["review_resolve_after"] = None
    elif license_plate == REJECTED_PLATE:
        effective["is_occupied"] = True
        effective["is_violation"] = True
        effective["review_status"] = None
        effective["review_resolve_after"] = None

    return effective


def find_spot_by_value(spots_ref, raw_value: str, *field_names: str):
    """Find the first parking spot whose configured identity matches any provided field name."""
    candidates = []
    for candidate in (raw_value.strip(), raw_value.strip().upper(), raw_value.strip().lower()):
        if candidate and candidate not in candidates:
            candidates.append(candidate)

    for field_name in field_names:
        for candidate in candidates:
            query = spots_ref.where(filter=FieldFilter(field_name, "==", candidate)).limit(1).get()
            for doc in query:
                return doc
    return None


def find_spot_by_mac(spots_ref, mac_address: str, *field_names: str):
    """Find the first parking spot whose configured MAC matches any provided field name."""
    return find_spot_by_value(spots_ref, mac_address, *field_names)


def normalize_mac(mac_address: str) -> str:
    return mac_address.strip().upper()


def normalize_identity(identity: str) -> str:
    return identity.strip().lower()


def get_display_command_ref(db, display_id: str):
    return db.collection(DISPLAY_COMMANDS_COLLECTION).document(normalize_identity(display_id))


def get_command_reference_time(command_data: dict):
    return command_data.get("claimed_at") or command_data.get("queued_at")


def is_stale_command(command_data: dict, now: datetime, stale_after_seconds: int = 30):
    reference_time = get_command_reference_time(command_data)
    age_seconds = seconds_since(reference_time, now)
    if age_seconds is None:
        return True
    return age_seconds > stale_after_seconds


def should_preserve_active_log_for_new_arrival(active_log_data: dict,
                                               spot_data_before: dict,
                                               now: datetime) -> bool:
    return should_preserve_recent_active_log(
        entry_time=active_log_data.get("entry_time"),
        license_plate=active_log_data.get("license_plate"),
        spot_last_seen=spot_data_before.get("last_seen"),
        now=now,
        preserve_window_seconds=CAMERA_FIRST_HEARTBEAT_GRACE_SECONDS,
        non_preservable_plates={
            RESOLVED_PLATE,
            REJECTED_PLATE,
            MANUAL_ACCEPTED_PLATE,
            "ABORTED"
        }
    )


def queue_display_command(db,
                          display_id: str,
                          spot_id: str,
                          title: str,
                          message: str,
                          *,
                          action: str = "SHOW_MESSAGE",
                          hold_ms: int = 4000):
    normalized_display_id = normalize_identity(display_id)
    command_ref = get_display_command_ref(db, normalized_display_id)
    existing_doc = command_ref.get()
    now = get_il_time()

    if existing_doc.exists:
        existing_data = existing_doc.to_dict() or {}
        if existing_data.get("status") in {"PENDING", "CLAIMED"} and not is_stale_command(existing_data, now):
            command_ref.update({
                "request_id": str(uuid.uuid4()),
                "action": action,
                "status": "PENDING",
                "display_id": normalized_display_id,
                "spot_id": spot_id,
                "title": title,
                "message": message,
                "hold_ms": hold_ms,
                "queued_at": now
            })
            refreshed_doc = command_ref.get()
            return refreshed_doc.to_dict() or {}

    command_data = {
        "request_id": str(uuid.uuid4()),
        "action": action,
        "status": "PENDING",
        "display_id": normalized_display_id,
        "spot_id": spot_id,
        "title": title,
        "message": message,
        "hold_ms": hold_ms,
        "queued_at": now
    }
    command_ref.set(command_data)
    return command_data


def claim_display_command(db, display_id: str):
    command_ref = get_display_command_ref(db, display_id)
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


def complete_display_command(db, display_id: str, request_id: str, status_text: str, detail: str | None):
    command_ref = get_display_command_ref(db, display_id)
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
def _extract_plate_digits(raw_text: str, detection_mode: str) -> str:
    logger.info(f"[OCR] {detection_mode} detected raw text:\n{raw_text}")
    plate = "".join(character for character in raw_text if character.isdigit())
    logger.info(f"[OCR] {detection_mode} extracted digits: '{plate}'")
    return plate


def _vision_text_from_response(response, detection_mode: str) -> str:
    if response.error.message:
        raise RuntimeError(f"{detection_mode} failed: {response.error.message}")

    texts = response.text_annotations
    if not texts:
        logger.info(f"[OCR] {detection_mode} found no text.")
        return ""

    return texts[0].description


def extract_license_plate(image_bytes: bytes) -> str:
    try:
        client = vision.ImageAnnotatorClient()
        image = vision.Image(content=image_bytes)

        for detection_mode, detector in (
            ("text_detection", client.text_detection),
            ("document_text_detection", client.document_text_detection),
        ):
            full_text = _vision_text_from_response(detector(image=image), detection_mode)
            if not full_text:
                continue

            plate = _extract_plate_digits(full_text, detection_mode)
            if plate:
                return plate

            logger.info(f"[OCR] {detection_mode} found text but no plate digits. Trying fallback if available.")

        logger.warning(
            "[OCR] Vision API found no usable plate text after text_detection and document_text_detection "
            f"for image payload ({len(image_bytes)} bytes)."
        )
    except Exception as e:
        logger.error(f"[OCR] Failed to extract license plate with Vision API: {str(e)}")

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


def get_display_id_for_spot(spot_id: str, spot_data: dict) -> str:
    configured_display_id = spot_data.get("display_id")
    if isinstance(configured_display_id, str) and configured_display_id.strip():
        return configured_display_id.strip()
    return f"display-{spot_id.lower()}"

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
        spot_id = spot_doc.id
        display_id = get_display_id_for_spot(spot_id, spot_data_before)

        # Find active parking log for this spot (no exit_time)
        logs_ref = db.collection("parking_logs")
        active_log_doc = get_latest_active_log_for_spot(logs_ref, spot_id)
        is_new_arrival = payload.is_occupied and not previous_is_occupied
        created_unidentified_log = False
        active_plate = None

        if payload.is_occupied:
            if is_new_arrival and active_log_doc:
                active_log_data = active_log_doc.to_dict() or {}
                if should_preserve_active_log_for_new_arrival(
                    active_log_data,
                    spot_data_before,
                    server_time
                ):
                    logger.info(
                        "Preserving recent active log for spot %s because the camera likely uploaded before the heartbeat.",
                        spot_id
                    )
                else:
                    logger.warning(
                        "Closing stale active log for spot %s before processing a new arrival.",
                        spot_id
                    )
                    active_log_doc.reference.update({"exit_time": server_time})
                    active_log_doc = None

            if not active_log_doc:
                logs_ref.add({
                    "spot_id": spot_id,
                    "license_plate": UNIDENTIFIED_PLATE,
                    "entry_time": server_time,
                    "exit_time": None,
                    "is_violation": True,
                    "user_id": None,
                    "snapshot_role": None
                })
                active_plate = UNIDENTIFIED_PLATE
                created_unidentified_log = True
                queue_display_command(
                    db,
                    display_id,
                    spot_id,
                    "Scanning",
                    "Please wait",
                    hold_ms=DISPLAY_SCANNING_HOLD_MS
                )
            elif active_log_doc:
                active_log_data = active_log_doc.to_dict() or {}
                active_plate = active_log_data.get("license_plate")
                if active_plate == UNIDENTIFIED_PLATE:
                    logger.info(
                        "Spot %s remains occupied with an active UNIDENTIFIED log; keeping manual review active.",
                        spot_id
                    )
                elif active_plate == REJECTED_PLATE:
                    queue_display_command(
                        db,
                        display_id,
                        spot_id,
                        "Access denied",
                        "Please remove car",
                        hold_ms=DISPLAY_REJECT_HOLD_MS
                    )
                else:
                    logger.info(
                        "Spot %s already has an active recognized or manually-decided log.",
                        spot_id
                    )
        elif not payload.is_occupied and active_log_doc:
            log_data = active_log_doc.to_dict()
            duration_seconds = seconds_since(log_data.get("entry_time"), server_time)
            if duration_seconds is None:
                duration_seconds = 60

            update_data = {"exit_time": server_time}
            active_plate = log_data.get("license_plate")

            if (duration_seconds < BOUNCY_DRIVER_MAX_SECONDS and
                    active_plate not in {RESOLVED_PLATE, REJECTED_PLATE, MANUAL_ACCEPTED_PLATE}):
                update_data["is_violation"] = False
                update_data["license_plate"] = "ABORTED"
                await broadcast_event("log_aborted", {"log_id": active_log_doc.id, "spot_id": spot_id})

            active_log_doc.reference.update(update_data)
            if active_plate == REJECTED_PLATE:
                queue_display_command(
                    db,
                    display_id,
                    spot_id,
                    "Spot clear",
                    "Thank you",
                    hold_ms=DISPLAY_SPOT_CLEARED_HOLD_MS
                )

        spot_update_data = {
            "last_seen": server_time,
            "battery_level": payload.battery_level,
            "is_occupied": payload.is_occupied
        }
        if not payload.is_occupied:
            spot_update_data.update(clear_review_flow_fields())
        elif active_plate == UNIDENTIFIED_PLATE:
            review_started_at = spot_data_before.get("review_started_at")
            if created_unidentified_log or not hasattr(review_started_at, "tzinfo"):
                review_started_at = server_time

            review_resolve_after = spot_data_before.get("review_resolve_after")
            if created_unidentified_log or not hasattr(review_resolve_after, "tzinfo"):
                review_resolve_after = build_review_deadline(review_started_at)

            spot_update_data.update({
                "review_started_at": review_started_at,
                "review_resolve_after": review_resolve_after,
                "review_status": "photo_review" if spot_data_before.get("review_capture_path") else "awaiting_capture"
            })
            if created_unidentified_log:
                spot_update_data.update(clear_review_capture_fields())
        elif active_plate == REJECTED_PLATE:
            spot_update_data.update(clear_review_metadata_fields())
        else:
            spot_update_data.update(clear_review_flow_fields())

        spot_doc.reference.update(spot_update_data)

        spot_data_dict = dict(spot_data_before)
        spot_data_dict.update({
            "is_occupied": payload.is_occupied,
            "last_seen": server_time,
            "battery_level": payload.battery_level
        })

        if not payload.is_occupied:
            spot_data_dict.pop("review_capture_path", None)
            spot_data_dict.pop("review_capture_at", None)
            spot_data_dict.pop("review_started_at", None)
            spot_data_dict.pop("review_resolve_after", None)
            spot_data_dict.pop("review_status", None)
        elif active_plate == UNIDENTIFIED_PLATE:
            spot_data_dict["review_started_at"] = spot_update_data.get("review_started_at")
            spot_data_dict["review_resolve_after"] = spot_update_data.get("review_resolve_after")
            spot_data_dict["review_status"] = spot_update_data.get("review_status")
            if created_unidentified_log:
                spot_data_dict.pop("review_capture_path", None)
                spot_data_dict.pop("review_capture_at", None)
        elif active_plate == REJECTED_PLATE:
            spot_data_dict.pop("review_started_at", None)
            spot_data_dict.pop("review_resolve_after", None)
            spot_data_dict.pop("review_status", None)
        else:
            spot_data_dict.pop("review_capture_path", None)
            spot_data_dict.pop("review_capture_at", None)
            spot_data_dict.pop("review_started_at", None)
            spot_data_dict.pop("review_resolve_after", None)
            spot_data_dict.pop("review_status", None)

        license_plate = None
        is_violation = False
        latest_active_log_doc = get_latest_active_log_for_spot(logs_ref, spot_id)
        if latest_active_log_doc:
            log_d = latest_active_log_doc.to_dict()
            license_plate = log_d.get("license_plate")
            is_violation = log_d.get("is_violation", False)
        review_status, review_resolve_after = get_review_status(
            license_plate,
            spot_data_dict,
            server_time
        )
        effective_state = build_effective_spot_state(
            payload.is_occupied,
            license_plate,
            is_violation,
            build_review_capture_url(spot_data_dict)
            if license_plate in {UNIDENTIFIED_PLATE, REJECTED_PLATE}
            else None,
            review_status,
            review_resolve_after
        )

        broadcast_spot = {
            "id": spot_id,
            "category": spot_data_dict.get("category"),
            "is_occupied": effective_state["is_occupied"],
            "license_plate": effective_state["license_plate"],
            "is_violation": effective_state["is_violation"],
            "battery_level": payload.battery_level,
            "last_seen": server_time.isoformat(),
            "review_capture_url": effective_state["review_capture_url"],
            "review_status": effective_state["review_status"],
            "review_resolve_after": effective_state["review_resolve_after"]
        }
        await broadcast_event("spot_update", {"spot": broadcast_spot})

    return {"status": "heartbeat_processed", "timestamp": server_time.isoformat()}



@app.post("/api/v1/displays/poll")
async def poll_display_command(payload: DisplayPollPayload, db = Depends(get_firestore_db)):
    command_data = claim_display_command(db, payload.display_id)
    if not command_data:
        return {"action": "IDLE"}

    queued_at = command_data.get("queued_at")
    claimed_at = command_data.get("claimed_at")
    return {
        "action": command_data.get("action", "IDLE"),
        "request_id": command_data.get("request_id"),
        "spot_id": command_data.get("spot_id"),
        "title": command_data.get("title"),
        "message": command_data.get("message"),
        "hold_ms": command_data.get("hold_ms", 4000),
        "queued_at": queued_at.isoformat() if hasattr(queued_at, "isoformat") else str(queued_at) if queued_at else None,
        "claimed_at": claimed_at.isoformat() if hasattr(claimed_at, "isoformat") else str(claimed_at) if claimed_at else None
    }


@app.post("/api/v1/displays/result")
async def complete_display_result(payload: DisplayCommandResultPayload, db = Depends(get_firestore_db)):
    success = complete_display_command(
        db,
        payload.display_id,
        payload.request_id,
        payload.status,
        payload.detail
    )
    if not success:
        raise HTTPException(status_code=404, detail="Matching display command not found")

    return {"status": "acknowledged", "request_id": payload.request_id}


@app.post("/api/v1/sensors/park", status_code=status.HTTP_202_ACCEPTED)
async def receive_park_event(
    camera_mac: str = Form(..., description="The MAC address of the camera node"),
    file: UploadFile = File(..., description="Image file from the ESP32-CAM"),
    db = Depends(get_firestore_db)
):
    server_time = get_il_time()

    image_bytes = await file.read()

    # Support both the new camera_mac schema and the older mac_address field.
    spots_ref = db.collection("parking_spots")
    spot_doc = find_spot_by_mac(spots_ref, camera_mac, "camera_mac", "mac_address")

    if not spot_doc:
        return build_gate_response("DENIED",
                                   "failed",
                                   "invalid camera",
                                   reason="invalid_camera_mac")
        
    spot_id = spot_doc.id
    spot_data = spot_doc.to_dict() or {}
    spot_category = spot_data.get("category")
    spot_ref = spot_doc.reference
    display_id = get_display_id_for_spot(spot_id, spot_data)
    logs_ref = db.collection("parking_logs")
    active_log_doc = get_latest_active_log_for_spot(logs_ref, spot_id)
    active_log_data = active_log_doc.to_dict() if active_log_doc else {}
    active_plate = active_log_data.get("license_plate")

    if active_plate == MANUAL_ACCEPTED_PLATE:
        spot_ref.update({
            "is_occupied": True,
            "last_seen": server_time,
            **clear_review_flow_fields()
        })
        return build_gate_response("WELCOME",
                                   "manual_accept",
                                   "admin approved",
                                   reason="already_manually_accepted")

    if active_plate == RESOLVED_PLATE:
        spot_ref.update({
            "is_occupied": True,
            "last_seen": server_time,
            **clear_review_flow_fields()
        })
        return build_gate_response("DENIED",
                                   "resolved",
                                   "resolved by admin",
                                   reason="already_resolved")

    if active_plate == REJECTED_PLATE:
        capture_data = save_review_capture_for_spot(spot_id, image_bytes)
        spot_ref.update({
            "is_occupied": True,
            "last_seen": server_time,
            **capture_data,
            **clear_review_metadata_fields()
        })
        spot_data.update(capture_data)
        await broadcast_event("spot_update", {"spot": {
            "id": spot_id,
            "category": spot_category,
            "is_occupied": True,
            "license_plate": REJECTED_PLATE,
            "is_violation": True,
            "battery_level": spot_data.get("battery_level"),
            "last_seen": server_time.isoformat(),
            "review_capture_url": build_review_capture_url(spot_data),
            "review_status": None,
            "review_resolve_after": None
        }})
        return build_gate_response("DENIED",
                                   "rejected",
                                   "please remove car",
                                   reason="already_rejected")

    if active_plate and active_plate != UNIDENTIFIED_PLATE:
        return build_gate_response(
            "DENIED" if active_log_data.get("is_violation", False) else "WELCOME",
            "already_processed",
            "already processed",
            plate=active_plate,
            is_violation=active_log_data.get("is_violation", False),
            reason="already_processed"
        )

    license_plate = extract_license_plate(image_bytes)

    if not license_plate:
        capture_data = save_review_capture_for_spot(spot_id, image_bytes)
        if not active_log_doc:
            logs_ref.add({
                "spot_id": spot_id,
                "license_plate": UNIDENTIFIED_PLATE,
                "entry_time": server_time,
                "exit_time": None,
                "is_violation": True,
                "user_id": None,
                "snapshot_role": None
            })

        review_started_at = spot_data.get("review_started_at")
        if not hasattr(review_started_at, "tzinfo"):
            review_started_at = server_time
        review_resolve_after = spot_data.get("review_resolve_after")
        if not hasattr(review_resolve_after, "tzinfo"):
            review_resolve_after = build_review_deadline(review_started_at)

        spot_ref.update({
            "is_occupied": True,
            "last_seen": server_time,
            **capture_data,
            "review_started_at": review_started_at,
            "review_resolve_after": review_resolve_after,
            "review_status": "photo_review"
        })
        spot_data.update(capture_data)
        spot_data.update({
            "review_started_at": review_started_at,
            "review_resolve_after": review_resolve_after,
            "review_status": "photo_review"
        })
        queue_display_command(
            db,
            display_id,
            spot_id,
            "Admin review",
            "Check dashboard",
            hold_ms=DISPLAY_MANUAL_REVIEW_HOLD_MS
        )
        await broadcast_event("spot_update", {"spot": {
            "id": spot_id,
            "category": spot_category,
            "is_occupied": True,
            "license_plate": UNIDENTIFIED_PLATE,
            "is_violation": True,
            "battery_level": spot_data.get("battery_level"),
            "last_seen": server_time.isoformat(),
            "review_capture_url": build_review_capture_url(spot_data),
            "review_status": "photo_review",
            "review_resolve_after": timestamp_to_iso(review_resolve_after)
        }})
        await broadcast_event("log_event", {"log": {
            "timestamp": server_time.isoformat(),
            "type": "unidentified",
            "message": f"Manual review needed at Spot {spot_id} because the plate could not be read."
        }})
        return build_gate_response("DENIED",
                                   "manual_review",
                                   "admin review",
                                   reason="could_not_read_plate")
        
    logger.info(f"Extracted plate {license_plate} from camera {camera_mac}")
    LPR_DEDUP_CACHE[license_plate] = server_time
    
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

    capture_base64 = base64.b64encode(image_bytes).decode("utf-8") if is_violation else None

    if active_log_doc and active_plate == UNIDENTIFIED_PLATE:
        update_data = {
            "license_plate": license_plate,
            "user_id": user_id,
            "snapshot_role": snapshot_role,
            "is_violation": is_violation
        }
        if capture_base64:
            update_data["capture_base64"] = capture_base64
        active_log_doc.reference.update(update_data)
        logger.info(f"Resolved UNIDENTIFIED review log for spot {spot_id} with plate {license_plate}")
        log_id = active_log_doc.id
    else:
        new_log_data = {
            "spot_id": spot_id,
            "license_plate": license_plate,
            "user_id": user_id,
            "snapshot_role": snapshot_role,
            "entry_time": server_time,
            "exit_time": None,
            "is_violation": is_violation
        }
        if capture_base64:
            new_log_data["capture_base64"] = capture_base64
        _, new_log_ref = logs_ref.add(new_log_data)
        log_id = new_log_ref.id
    
    spot_ref.update({
        "is_occupied": True,
        "last_seen": server_time,
        **clear_review_flow_fields()
    })
    spot_data.pop("review_capture_path", None)
    spot_data.pop("review_capture_at", None)
    spot_data.pop("review_started_at", None)
    spot_data.pop("review_resolve_after", None)
    spot_data.pop("review_status", None)

    broadcast_spot_data = {
        "id": spot_id,
        "category": spot_category,
        "is_occupied": True,
        "license_plate": license_plate,
        "is_violation": is_violation,
        "battery_level": spot_data.get("battery_level"),
        "last_seen": server_time.isoformat(),
        "review_capture_url": None,
        "review_status": None,
        "review_resolve_after": None
    }
    await broadcast_event("spot_update", {"spot": broadcast_spot_data})

    if is_violation:
        await broadcast_event("log_event", {"log": {
            "log_id": log_id,
            "spot_id": spot_id,
            "timestamp": server_time.isoformat(), 
            "type": "unidentified" if license_plate == UNIDENTIFIED_PLATE else "violation", 
            "message": f"Violation at Spot {spot_id} by {license_plate}"
        }})

    action = "DENIED" if is_violation else "WELCOME"
    queue_display_command(
        db,
        display_id,
        spot_id,
        "Access denied" if is_violation else "Welcome",
        display_message,
        hold_ms=DISPLAY_WELCOME_HOLD_MS
    )
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
        current_entry_time = log_data.get("entry_time")
        current_entry_timestamp = current_entry_time.timestamp() if hasattr(current_entry_time, "timestamp") else float("-inf")
        existing_log = active_logs_by_spot.get(log_spot_id)
        existing_entry_time = existing_log.get("entry_time") if existing_log else None
        existing_entry_timestamp = existing_entry_time.timestamp() if hasattr(existing_entry_time, "timestamp") else float("-inf")

        if current_entry_timestamp >= existing_entry_timestamp:
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
        review_status, review_resolve_after = get_review_status(
            license_plate,
            s,
            get_il_time()
        )
        effective_state = build_effective_spot_state(
            is_occupied,
            license_plate,
            is_violation,
            build_review_capture_url(s)
            if license_plate in {UNIDENTIFIED_PLATE, REJECTED_PLATE}
            else None,
            review_status,
            review_resolve_after
        )
        
        if user_role == "admin":
            result.append({
                "id": spot_id,
                "category": category,
                "is_occupied": effective_state["is_occupied"],
                "license_plate": effective_state["license_plate"] if effective_state["is_occupied"] else None,
                "is_violation": effective_state["is_violation"] if effective_state["is_occupied"] else False,
                "battery_level": battery_level,
                "last_seen": last_seen.isoformat() if hasattr(last_seen, 'isoformat') else str(last_seen) if last_seen else None,
                "review_capture_url": effective_state["review_capture_url"],
                "review_status": effective_state["review_status"],
                "review_resolve_after": effective_state["review_resolve_after"]
            })
        elif category == user_role or (current_user.get("is_special_needs") and category == "special-needs-driver"):
            result.append({
                "id": spot_id,
                "category": category,
                "is_occupied": effective_state["is_occupied"],
                "license_plate": None,
                "is_violation": False,
                "last_seen": last_seen.isoformat() if hasattr(last_seen, 'isoformat') else str(last_seen) if last_seen else None
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
        
        if license_plate == UNIDENTIFIED_PLATE:
            msg_type = "unidentified"
            msg = f"Manual review is active at Spot {spot_id}."
        elif license_plate == RESOLVED_PLATE:
            msg_type = "info"
            msg = f"Admin resolved anomaly at Spot {spot_id}."
        elif license_plate == MANUAL_ACCEPTED_PLATE:
            msg_type = "info"
            msg = f"Admin manually accepted vehicle at Spot {spot_id}."
        elif license_plate == REJECTED_PLATE:
            msg_type = "violation"
            msg = f"Violation at Spot {spot_id} (Unidentified Plate)"
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
            "log_id": doc.id,
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


@app.get("/api/v1/admin/usage-stats")
async def get_usage_stats(admin_user: dict = Depends(get_current_admin), db = Depends(get_firestore_db)):
    spots_docs = db.collection("parking_spots").get()
    logs_docs = db.collection("parking_logs").get()

    total_spots = 0
    occupied_spots = 0
    for spot_doc in spots_docs:
        total_spots += 1
        if spot_doc.to_dict().get("is_occupied", False):
            occupied_spots += 1

    total_logs = 0
    authorized_sessions = 0
    violation_events = 0
    unresolved_events = 0
    resolved_events = 0
    aborted_events = 0
    hour_counter = Counter()
    spot_counter = Counter()
    completed_durations_minutes = []

    for log_doc in logs_docs:
        total_logs += 1
        log_data = log_doc.to_dict()
        spot_id = log_data.get("spot_id")
        license_plate = log_data.get("license_plate")
        is_violation = bool(log_data.get("is_violation", False))
        entry_time = log_data.get("entry_time")
        exit_time = log_data.get("exit_time")

        if spot_id:
            spot_counter[spot_id] += 1

        if hasattr(entry_time, "astimezone"):
            localized_entry = entry_time.astimezone(IL_TIMEZONE) if IL_TIMEZONE else entry_time.astimezone()
            hour_counter[localized_entry.hour] += 1

        if hasattr(entry_time, "timestamp") and hasattr(exit_time, "timestamp"):
            duration_minutes = max(0.0, (exit_time - entry_time).total_seconds() / 60.0)
            completed_durations_minutes.append(duration_minutes)

        if license_plate == UNIDENTIFIED_PLATE:
            unresolved_events += 1
        elif license_plate == RESOLVED_PLATE:
            resolved_events += 1
        elif license_plate == MANUAL_ACCEPTED_PLATE:
            authorized_sessions += 1
        elif license_plate == REJECTED_PLATE:
            violation_events += 1
        elif license_plate == "ABORTED":
            aborted_events += 1
        elif is_violation:
            violation_events += 1
        else:
            authorized_sessions += 1

    peak_hour_label = None
    if hour_counter:
        peak_hour = hour_counter.most_common(1)[0][0]
        peak_hour_label = f"{peak_hour:02d}:00-{peak_hour:02d}:59"

    busiest_spot = spot_counter.most_common(1)[0][0] if spot_counter else None
    average_duration_minutes = None
    if completed_durations_minutes:
        average_duration_minutes = round(
            sum(completed_durations_minutes) / len(completed_durations_minutes), 1
        )

    return {
        "total_spots": total_spots,
        "occupied_spots": occupied_spots,
        "total_logs": total_logs,
        "authorized_sessions": authorized_sessions,
        "violation_events": violation_events,
        "unresolved_events": unresolved_events,
        "resolved_events": resolved_events,
        "aborted_events": aborted_events,
        "peak_hour": peak_hour_label,
        "busiest_spot": busiest_spot,
        "average_duration_minutes": average_duration_minutes,
        "generated_at": get_il_time().isoformat(),
    }


@app.put("/api/v1/sensors/accept")
async def accept_spot(payload: ResolvePayload, admin_user: dict = Depends(get_current_admin), db = Depends(get_firestore_db)):
    logs_ref = db.collection("parking_logs")
    active_logs_query = list(
        logs_ref
        .where(filter=FieldFilter("spot_id", "==", payload.spot_id))
        .where(filter=FieldFilter("license_plate", "==", UNIDENTIFIED_PLATE))
        .where(filter=FieldFilter("exit_time", "==", None))
        .get()
    )

    if not active_logs_query:
        raise HTTPException(
            status_code=404,
            detail=f"No active UNIDENTIFIED anomaly found for spot {payload.spot_id}"
        )

    for log_doc in active_logs_query:
        log_doc.reference.update({
            "is_violation": False,
            "license_plate": MANUAL_ACCEPTED_PLATE,
            "snapshot_role": "admin_manual_accept",
            "user_id": admin_user.get("user_id")
        })

    spot_ref = db.collection("parking_spots").document(payload.spot_id)
    spot_doc = spot_ref.get()

    if spot_doc.exists:
        spot_data = spot_doc.to_dict() or {}
        spot_ref.update(clear_review_flow_fields())
        queue_display_command(
            db,
            get_display_id_for_spot(payload.spot_id, spot_data),
            payload.spot_id,
            "Welcome",
            "Admin approved",
            hold_ms=DISPLAY_WELCOME_HOLD_MS
        )
        last_seen_raw = spot_data.get("last_seen")
        await broadcast_event("spot_update", {"spot": {
            "id": spot_doc.id,
            "category": spot_data.get("category"),
            "is_occupied": True,
            "license_plate": MANUAL_ACCEPTED_PLATE,
            "is_violation": False,
            "battery_level": spot_data.get("battery_level"),
            "last_seen": last_seen_raw.isoformat() if hasattr(last_seen_raw, 'isoformat') else str(last_seen_raw) if last_seen_raw else None,
            "review_capture_url": None,
            "review_status": None,
            "review_resolve_after": None
        }})
        await broadcast_event("log_event", {"log": {
            "timestamp": get_il_time().isoformat(),
            "type": "info",
            "message": f"Admin {admin_user.get('name')} manually accepted vehicle at spot {payload.spot_id}."
        }})

    return {"status": "accepted", "spot_id": payload.spot_id}


@app.put("/api/v1/sensors/reject")
async def reject_spot(payload: ResolvePayload, admin_user: dict = Depends(get_current_admin), db = Depends(get_firestore_db)):
    logs_ref = db.collection("parking_logs")
    active_logs_query = list(
        logs_ref
        .where(filter=FieldFilter("spot_id", "==", payload.spot_id))
        .where(filter=FieldFilter("license_plate", "==", UNIDENTIFIED_PLATE))
        .where(filter=FieldFilter("exit_time", "==", None))
        .get()
    )

    if not active_logs_query:
        raise HTTPException(
            status_code=404,
            detail=f"No active UNIDENTIFIED anomaly found for spot {payload.spot_id}"
        )

    safe_spot_id = "".join(
        ch for ch in payload.spot_id.strip().lower() if ch.isalnum() or ch in {"-", "_"}
    ) or "spot"
    capture_doc = db.collection("spot_captures").document(safe_spot_id).get()
    capture_base64 = capture_doc.to_dict().get("image_base64") if capture_doc.exists else None

    for log_doc in active_logs_query:
        update_data = {
            "is_violation": True,
            "license_plate": REJECTED_PLATE
        }
        if capture_base64:
            update_data["capture_base64"] = capture_base64
        log_doc.reference.update(update_data)

    spot_ref = db.collection("parking_spots").document(payload.spot_id)
    spot_doc = spot_ref.get()

    if spot_doc.exists:
        spot_data = spot_doc.to_dict() or {}
        review_capture_url = build_review_capture_url(spot_data)
        spot_ref.update(clear_review_metadata_fields())
        queue_display_command(
            db,
            get_display_id_for_spot(payload.spot_id, spot_data),
            payload.spot_id,
            "Access denied",
            "Please remove car",
            hold_ms=DISPLAY_REJECT_HOLD_MS
        )
        last_seen_raw = spot_data.get("last_seen")
        await broadcast_event("spot_update", {"spot": {
            "id": spot_doc.id,
            "category": spot_data.get("category"),
            "is_occupied": spot_data.get("is_occupied", False),
            "license_plate": REJECTED_PLATE,
            "is_violation": True,
            "battery_level": spot_data.get("battery_level"),
            "last_seen": last_seen_raw.isoformat() if hasattr(last_seen_raw, 'isoformat') else str(last_seen_raw) if last_seen_raw else None,
            "review_capture_url": review_capture_url,
            "review_status": None,
            "review_resolve_after": None
        }})
        await broadcast_event("log_event", {"log": {
            "log_id": log_doc.id,
            "timestamp": get_il_time().isoformat(),
            "type": "violation",
            "message": f"Violation at Spot {payload.spot_id} (Unidentified Plate)"
        }})

    return {"status": "rejected", "spot_id": payload.spot_id}

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
    spot_data = spot_doc.to_dict() or {}
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
                "license_plate": UNIDENTIFIED_PLATE,
                "entry_time": event_time,
                "exit_time": None,
                "is_violation": True,
                "user_id": None,
                "snapshot_role": None
            })
        elif not is_occupied and active_log_doc:
            log_data = active_log_doc.to_dict()
            duration_seconds = seconds_since(log_data.get("entry_time"), event_time)
            if duration_seconds is None:
                duration_seconds = 60
                
            update_data = {"exit_time": event_time}
            active_plate = log_data.get("license_plate")
            if (duration_seconds < BOUNCY_DRIVER_MAX_SECONDS and
                    active_plate not in {RESOLVED_PLATE, REJECTED_PLATE, MANUAL_ACCEPTED_PLATE}):
                update_data["is_violation"] = False
                update_data["license_plate"] = "ABORTED"
                await broadcast_event("log_aborted", {"log_id": active_log_doc.id, "spot_id": spot_id})
                
            active_log_doc.reference.update(update_data)
            
    if events:
        last_event = events[-1]
        last_event_time = datetime.fromtimestamp(last_event.t, tz=IL_TIMEZONE) if IL_TIMEZONE else datetime.fromtimestamp(last_event.t).astimezone()
        spot_update_data = {
            "is_occupied": last_event.v,
            "last_seen": get_il_time()
        }
        if not last_event.v:
            spot_update_data.update(clear_review_flow_fields())
        else:
            latest_active_log_doc = get_latest_active_log_for_spot(logs_ref, spot_id)
            latest_active_log = latest_active_log_doc.to_dict() if latest_active_log_doc else {}
            if latest_active_log.get("license_plate") == UNIDENTIFIED_PLATE:
                review_started_at = spot_data.get("review_started_at")
                if not hasattr(review_started_at, "tzinfo"):
                    review_started_at = last_event_time
                review_resolve_after = spot_data.get("review_resolve_after")
                if not hasattr(review_resolve_after, "tzinfo"):
                    review_resolve_after = build_review_deadline(review_started_at)
                spot_update_data.update({
                    "review_started_at": review_started_at,
                    "review_resolve_after": review_resolve_after,
                    "review_status": "awaiting_capture"
                })
            else:
                spot_update_data.update(clear_review_flow_fields())
        spot_doc.reference.update(spot_update_data)
        
        # Build updated spot data for SSE broadcast
        spot_data_dict = spot_doc.to_dict()
        spot_data_dict.update({
            "is_occupied": last_event.v,
            "last_seen": get_il_time()
        })
        if not last_event.v:
            spot_data_dict.pop("review_capture_path", None)
            spot_data_dict.pop("review_capture_at", None)
            spot_data_dict.pop("review_started_at", None)
            spot_data_dict.pop("review_resolve_after", None)
            spot_data_dict.pop("review_status", None)
        
        license_plate = None
        is_violation = False
        latest_active_log_doc = get_latest_active_log_for_spot(logs_ref, spot_id)
        if latest_active_log_doc:
            log_d = latest_active_log_doc.to_dict()
            license_plate = log_d.get("license_plate")
            is_violation = log_d.get("is_violation", False)
        review_status, review_resolve_after = get_review_status(
            license_plate,
            spot_data_dict,
            get_il_time()
        )
        effective_state = build_effective_spot_state(
            last_event.v,
            license_plate,
            is_violation,
            build_review_capture_url(spot_data_dict)
            if license_plate in {UNIDENTIFIED_PLATE, REJECTED_PLATE}
            else None,
            review_status,
            review_resolve_after
        )
        
        broadcast_spot = {
            "id": spot_id,
            "category": spot_data_dict.get("category"),
            "is_occupied": effective_state["is_occupied"],
            "license_plate": effective_state["license_plate"],
            "is_violation": effective_state["is_violation"],
            "battery_level": spot_data_dict.get("battery_level"),
            "last_seen": get_il_time().isoformat(),
            "review_capture_url": effective_state["review_capture_url"],
            "review_status": effective_state["review_status"],
            "review_resolve_after": effective_state["review_resolve_after"]
        }
        await broadcast_event("spot_update", {"spot": broadcast_spot})

    return {"status": "bulk_processed", "events": len(payload.data)}

frontend_dir = os.path.join(os.path.dirname(__file__), "../Frontend")
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
