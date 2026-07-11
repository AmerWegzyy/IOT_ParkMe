#!/usr/bin/env python3
"""
simulate_spots.py — Simulate a whole parking lot with no extra hardware.

We own one physical sensor+camera pair (spot C1). This script impersonates the
OTHER seeded spots (A1, A2, B1, B2, C2) so the dashboard shows a realistic,
busy parking lot: cars arrive, get photographed (real images through the real
OCR pipeline), stay a while, and leave. It talks to the SAME endpoints the
real boards use, so everything downstream (OCR, authorization, violations,
manual review, SSE, statistics) is exercised for real.

  Heartbeats -> POST /api/v1/sensors/heartbeat  (like the sensor node)
  Photos     -> POST /api/v1/sensors/park       (like the camera node)

Usage (defaults target the live cloud backend):

  python simulate_spots.py                       # all fake spots, photos on
  python simulate_spots.py --local               # against http://127.0.0.1:8000
  python simulate_spots.py --spots A1,B1         # only some spots
  python simulate_spots.py --no-photos           # occupancy only (will create
                                                 #   manual-review logs after 30s!)
  python simulate_spots.py --offline-demo A2     # A2 goes silent mid-run to
                                                 #   demonstrate OFFLINE detection
  python simulate_spots.py --fast                # quick demo pacing

Safe by design: only sends heartbeats/photos (normal runtime traffic). Never
seeds, never deletes, never touches spot C1 (the real hardware) unless you
explicitly pass it in --spots.

Stdlib only — no pip installs needed.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

CLOUD_URL = "https://parkme-backend-31114651685.me-west1.run.app"
LOCAL_URL = "http://127.0.0.1:8000"

# Seeded spots (Backend/seed_firestore.py). C1 is the real hardware — excluded
# by default so the simulator never fights the physical boards.
SEEDED_SPOTS = {
    "A1": {"sensor_mac": "AA:BB:CC:DD:EE:01", "camera_mac": "FF:EE:DD:CC:BB:01", "category": "student"},
    "A2": {"sensor_mac": "AA:BB:CC:DD:EE:02", "camera_mac": "FF:EE:DD:CC:BB:02", "category": "lecturer"},
    "B1": {"sensor_mac": "AA:BB:CC:DD:EE:03", "camera_mac": "FF:EE:DD:CC:BB:03", "category": "special-needs-driver"},
    "B2": {"sensor_mac": "AA:BB:CC:DD:EE:04", "camera_mac": "FF:EE:DD:CC:BB:04", "category": "staff"},
    "C1": {"sensor_mac": "A8:42:E3:46:F4:E0", "camera_mac": "24:6F:28:47:F9:E8", "category": "student"},
    "C2": {"sensor_mac": "AA:BB:CC:DD:EE:06", "camera_mac": "FF:EE:DD:CC:BB:06", "category": "lecturer"},
}
DEFAULT_SPOTS = ["A1", "A2", "B1", "B2", "C2"]

TEST_PICS_DIR = Path(__file__).resolve().parent.parent / "tests" / "test_pics"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def post_json(url: str, payload: dict, timeout: int = 10) -> int:
    body = json.dumps(payload).encode("utf-8")
    req = Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    with urlopen(req, timeout=timeout) as resp:
        return resp.status


def post_photo(url: str, camera_mac: str, image_path: Path, timeout: int = 20) -> tuple[int, dict]:
    """Multipart upload exactly like the ESP32-CAM does."""
    boundary = f"----ParkMeSimBoundary{uuid.uuid4().hex}"
    file_bytes = image_path.read_bytes()

    body = bytearray()
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(f'Content-Disposition: form-data; name="camera_mac"\r\n\r\n{camera_mac}\r\n'.encode())
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(f'Content-Disposition: form-data; name="file"; filename="{image_path.name}"\r\n'.encode())
    body.extend(b"Content-Type: image/jpeg\r\n\r\n")
    body.extend(file_bytes)
    body.extend(f"\r\n--{boundary}--\r\n".encode())

    req = Request(url, data=bytes(body), method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    try:
        with urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8", errors="replace") or "{}")
    except HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8", errors="replace") or "{}")
        except Exception:
            return e.code, {}


class SimulatedSpot:
    """One fake sensor+camera pair driven by a tiny state machine."""

    def __init__(self, spot_id: str, config: dict, args, images: list[Path]):
        self.spot_id = spot_id
        self.sensor_mac = config["sensor_mac"]
        self.camera_mac = config["camera_mac"]
        self.category = config["category"]
        self.args = args
        self.images = images
        self.occupied = False
        self.battery = random.uniform(55.0, 98.0)
        self.next_heartbeat_at = 0.0
        self.state_change_at = time.time() + random.uniform(2, args.max_idle)
        self.silenced = False  # --offline-demo

    def heartbeat(self, server: str) -> None:
        payload = {
            "mac_address": self.sensor_mac,
            "is_occupied": self.occupied,
            "battery_level": round(self.battery, 1),
        }
        try:
            status = post_json(f"{server}/api/v1/sensors/heartbeat", payload)
            log(f"{self.spot_id}: heartbeat {'OCCUPIED' if self.occupied else 'FREE':8s} "
                f"battery {self.battery:5.1f}% -> {status}")
        except (URLError, TimeoutError, OSError) as e:
            log(f"{self.spot_id}: heartbeat FAILED ({e})")
        self.next_heartbeat_at = time.time() + self.args.heartbeat
        self.battery = max(5.0, self.battery - 0.05)

    def upload_photo(self, server: str) -> None:
        if not self.args.photos or not self.images:
            return
        image = random.choice(self.images)
        try:
            status, resp = post_photo(f"{server}/api/v1/sensors/park", self.camera_mac, image)
            plate = resp.get("plate") or resp.get("status") or "?"
            log(f"{self.spot_id}: photo {image.name} -> {status} ({plate})")
        except (URLError, TimeoutError, OSError) as e:
            log(f"{self.spot_id}: photo upload FAILED ({e})")

    def tick(self, server: str, now: float) -> None:
        if self.silenced:
            return  # simulating a dead sensor: total radio silence

        if now >= self.state_change_at:
            self.occupied = not self.occupied
            if self.occupied:
                log(f"{self.spot_id}: >>> car arrives")
                self.heartbeat(server)          # immediate heartbeat on change,
                self.upload_photo(server)       # then the camera photo,
                stay = random.uniform(self.args.min_stay, self.args.max_stay)
                self.state_change_at = now + stay
                log(f"{self.spot_id}: staying {stay:.0f}s")
            else:
                log(f"{self.spot_id}: <<< car leaves")
                self.heartbeat(server)
                self.state_change_at = now + random.uniform(5, self.args.max_idle)
        elif now >= self.next_heartbeat_at:
            self.heartbeat(server)


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate seeded ParkMe spots against the backend.")
    parser.add_argument("--server-url", default=CLOUD_URL, help=f"Backend base URL (default: cloud)")
    parser.add_argument("--local", action="store_true", help=f"Shortcut for --server-url {LOCAL_URL}")
    parser.add_argument("--spots", default=",".join(DEFAULT_SPOTS),
                        help="Comma-separated spot ids to simulate (default: all fake spots; C1 excluded)")
    parser.add_argument("--heartbeat", type=float, default=15.0, help="Heartbeat interval seconds (default 15)")
    parser.add_argument("--min-stay", type=float, default=120.0, help="Min parking duration (default 120s; "
                        "under 90s the backend correctly logs ABORTED)")
    parser.add_argument("--max-stay", type=float, default=300.0, help="Max parking duration (default 300s)")
    parser.add_argument("--max-idle", type=float, default=90.0, help="Max time a spot stays free (default 90s)")
    parser.add_argument("--no-photos", dest="photos", action="store_false",
                        help="Skip camera uploads (occupied spots will hit the 30s manual-review deadline!)")
    parser.add_argument("--fast", action="store_true", help="Compressed pacing for a quick demo")
    parser.add_argument("--offline-demo", metavar="SPOT",
                        help="After 60s, this spot goes silent for 180s to demo OFFLINE detection (needs >120s)")
    parser.add_argument("--duration", type=float, default=0, help="Stop after N seconds (default: run until Ctrl+C)")
    args = parser.parse_args()

    if args.local:
        args.server_url = LOCAL_URL
    server = args.server_url.rstrip("/")

    if args.fast:
        args.heartbeat, args.min_stay, args.max_stay, args.max_idle = 8.0, 100.0, 150.0, 20.0

    images = sorted(p for p in TEST_PICS_DIR.iterdir()
                    if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS) if TEST_PICS_DIR.is_dir() else []
    if args.photos and not images:
        log(f"WARNING: no images in {TEST_PICS_DIR}; continuing without photos.")
        args.photos = False

    spot_ids = [s.strip().upper() for s in args.spots.split(",") if s.strip()]
    unknown = [s for s in spot_ids if s not in SEEDED_SPOTS]
    if unknown:
        sys.exit(f"Unknown spot id(s): {unknown}. Seeded spots: {list(SEEDED_SPOTS)}")
    if "C1" in spot_ids:
        log("WARNING: simulating C1 — this will fight the REAL hardware if it is powered on.")

    spots = [SimulatedSpot(s, SEEDED_SPOTS[s], args, images) for s in spot_ids]
    log(f"Simulating {spot_ids} against {server} (photos {'ON' if args.photos else 'OFF'}). Ctrl+C to stop.")
    log("Open the dashboard to watch the spots come alive.")

    started = time.time()
    offline_started = False
    offline_ended = False

    try:
        while True:
            now = time.time()

            if args.offline_demo:
                target = next((s for s in spots if s.spot_id == args.offline_demo.upper()), None)
                if target:
                    if not offline_started and now - started > 60:
                        target.silenced = True
                        offline_started = True
                        log(f"{target.spot_id}: === SIMULATING SENSOR FAILURE (silent for 180s; "
                            f"dashboard flags OFFLINE after 120s) ===")
                    elif offline_started and not offline_ended and now - started > 240:
                        target.silenced = False
                        target.next_heartbeat_at = 0
                        offline_ended = True
                        log(f"{target.spot_id}: === SENSOR RECOVERED ===")

            for spot in spots:
                spot.tick(server, now)

            if args.duration and now - started > args.duration:
                log("Duration reached, stopping.")
                break
            time.sleep(1.0)
    except KeyboardInterrupt:
        log("Stopping. Sending a final FREE heartbeat for every simulated spot...")
        for spot in spots:
            spot.silenced = False
            spot.occupied = False
            spot.heartbeat(server)
        log("Done — simulated spots left clean (FREE).")


if __name__ == "__main__":
    main()
