#!/usr/bin/env python3
"""
test_parallel_spots.py — ParkMe Backend Parallelism / Concurrency Validation

PURPOSE:
    Verify that the deployed backend correctly handles MULTIPLE parking spots
    generating camera images SIMULTANEOUSLY — each spot uploading its own image
    at the same instant — with no cross-contamination between spots.

    This exercises the exact scenario a real lot produces at rush hour: several
    cars arrive at once, several ESP32-CAM nodes fire at once, and the backend
    must attribute each photo to the right spot and return the right plate to
    the right camera.

WHAT IT CHECKS (per spot, per round):
    1. The occupied heartbeat is accepted (HTTP 202).
    2. The simultaneous photo upload is accepted (HTTP 200/202).
    3. The plate the server extracted matches the plate encoded in the image
       filename that THIS spot uploaded.
    4. CROSS-TALK detection: the returned plate must NOT be the plate that a
       DIFFERENT spot uploaded in the same simultaneous burst. A cross-talk hit
       means concurrent requests leaked state between spots — the one failure
       mode this test exists to catch.

RESULT CLASSIFICATION:
    [PASS]        plate matches this spot's own image             -> parallelism OK
    [CROSS_TALK]  plate belongs to ANOTHER spot's image           -> PARALLELISM BUG
    [OCR_MISS]    no plate extracted (manual review)              -> OCR noise, not a
                                                                     parallelism failure
    [OCR_MISREAD] wrong plate, but not any other spot's plate     -> OCR noise
    [ERROR]       network / HTTP error                            -> infrastructure

    The final verdict is PASS if there are zero CROSS_TALK and zero ERROR
    results. OCR misses/misreads are reported but do not fail the run (the LPR
    accuracy suite `test_lpr_pipeline.py` covers OCR quality separately).

HOW SIMULTANEITY IS ACHIEVED:
    One thread per spot; every thread builds its full HTTP request, then blocks
    on a shared threading.Barrier. When the last thread arrives, all requests
    fire in the same instant. Heartbeats are synchronized the same way.

USAGE:
    # against the live cloud backend (default)
    python tests/test_parallel_spots.py

    # against a local backend
    python tests/test_parallel_spots.py --local

    # more rounds (images rotate between spots each round), custom spots
    python tests/test_parallel_spots.py --rounds 3 --spots A1,A2,B2

    # also measure a sequential baseline for a wall-clock comparison
    python tests/test_parallel_spots.py --baseline

SAFETY:
    Uses only the seeded FAKE spots (A1, A2, B1, B2, C2) — never C1, the real
    hardware. Sends only normal runtime traffic (heartbeats + photo uploads)
    through the same endpoints the real boards use; never seeds or deletes
    anything. Every simulated spot is left FREE on exit (including Ctrl+C).

    NOTE: like test_lpr_pipeline.py, this writes real parking logs to the live
    Firestore database — fine for the dev/course database, don't run mid-demo.

    Stdlib only — no pip installs needed.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

CLOUD_URL = "https://parkme-backend-31114651685.me-west1.run.app"
LOCAL_URL = "http://127.0.0.1:8000"

# Seeded fake spots (Backend/seed_firestore.py). C1 (real hardware) is
# deliberately NOT in this table so it can never be targeted.
FAKE_SPOTS = {
    "A1": {"sensor_mac": "AA:BB:CC:DD:EE:01", "camera_mac": "FF:EE:DD:CC:BB:01"},
    "A2": {"sensor_mac": "AA:BB:CC:DD:EE:02", "camera_mac": "FF:EE:DD:CC:BB:02"},
    "B1": {"sensor_mac": "AA:BB:CC:DD:EE:03", "camera_mac": "FF:EE:DD:CC:BB:03"},
    "B2": {"sensor_mac": "AA:BB:CC:DD:EE:04", "camera_mac": "FF:EE:DD:CC:BB:04"},
    "C2": {"sensor_mac": "AA:BB:CC:DD:EE:06", "camera_mac": "FF:EE:DD:CC:BB:06"},
}
DEFAULT_SPOTS = ["A1", "A2", "B1", "B2", "C2"]

TEST_PICS_DIR = Path(__file__).resolve().parent / "test_pics"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

# Images the LPR suite has flagged as unreliable on record (misreads / manual
# review). Kept out of the assignment pool so OCR noise doesn't cloud the
# parallelism verdict; everything else in tests/test_pics/ is fair game.
KNOWN_TRICKY_IMAGES = {"9656026.jpg", "4528139.jpg"}


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def normalize_plate(raw: Optional[str]) -> str:
    if not raw:
        return ""
    return "".join(ch for ch in str(raw) if ch.isdigit())


@dataclass
class SpotResult:
    spot_id: str
    image_name: str
    expected_plate: str
    extracted_plate: str = ""
    heartbeat_status: int = 0
    upload_status: int = 0
    latency_seconds: float = 0.0
    classification: str = "ERROR"  # PASS / CROSS_TALK / OCR_MISS / OCR_MISREAD / ERROR
    notes: str = ""


@dataclass
class RoundResult:
    round_number: int
    mode: str  # "parallel" or "sequential"
    wall_clock_seconds: float = 0.0
    spot_results: list[SpotResult] = field(default_factory=list)


def post_json(url: str, payload: dict, timeout: int = 15) -> int:
    body = json.dumps(payload).encode("utf-8")
    req = Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    with urlopen(req, timeout=timeout) as resp:
        return resp.status


def build_multipart_request(url: str, camera_mac: str, image_path: Path) -> Request:
    """Build (but do not send) the multipart upload, exactly like the ESP32-CAM."""
    boundary = f"----ParkMeParBoundary{uuid.uuid4().hex}"
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
    return req


def send_photo_request(req: Request, timeout: int = 45) -> tuple[int, dict]:
    try:
        with urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8", errors="replace") or "{}")
    except HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8", errors="replace") or "{}")
        except Exception:
            return e.code, {}


def free_heartbeat(server: str, spot_id: str, timeout: int = 10) -> None:
    """Send is_occupied=False so the spot's active log closes and OCR runs fresh next time."""
    try:
        post_json(
            f"{server}/api/v1/sensors/heartbeat",
            {"mac_address": FAKE_SPOTS[spot_id]["sensor_mac"], "is_occupied": False, "battery_level": 100.0},
            timeout=timeout,
        )
    except (URLError, TimeoutError, OSError) as e:
        log(f"{spot_id}: cleanup FREE heartbeat failed ({e})")


def pick_images(spot_ids: list[str], round_number: int) -> dict[str, Path]:
    """Assign a DISTINCT image to each spot; rotate assignment each round."""
    if not TEST_PICS_DIR.is_dir():
        sys.exit(f"ERROR: test images directory not found: {TEST_PICS_DIR}")

    candidates = sorted(
        p for p in TEST_PICS_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS and p.name not in KNOWN_TRICKY_IMAGES
    )
    if len(candidates) < len(spot_ids):
        sys.exit(f"ERROR: need at least {len(spot_ids)} distinct images in {TEST_PICS_DIR}, found {len(candidates)}")

    offset = (round_number * len(spot_ids)) % len(candidates)
    rotated = candidates[offset:] + candidates[:offset]
    return {spot_id: rotated[i] for i, spot_id in enumerate(spot_ids)}


def run_spot_cycle(server: str,
                   spot_id: str,
                   image_path: Path,
                   heartbeat_barrier: Optional[threading.Barrier],
                   upload_barrier: Optional[threading.Barrier]) -> SpotResult:
    """One spot's full arrival: occupied heartbeat, then the photo upload.

    With barriers (parallel mode) every spot fires each phase in the same
    instant; with barriers=None (sequential baseline) it just runs.
    """
    result = SpotResult(
        spot_id=spot_id,
        image_name=image_path.name,
        expected_plate=normalize_plate(image_path.stem),
    )
    config = FAKE_SPOTS[spot_id]

    # Phase 1 — occupied heartbeat (the "car arrived" signal from the sensor node)
    heartbeat_payload = {
        "mac_address": config["sensor_mac"],
        "is_occupied": True,
        "battery_level": 88.0,
    }
    try:
        if heartbeat_barrier is not None:
            heartbeat_barrier.wait(timeout=30)
        result.heartbeat_status = post_json(f"{server}/api/v1/sensors/heartbeat", heartbeat_payload)
    except Exception as e:
        result.notes = f"heartbeat failed: {e}"
        return result

    # Phase 2 — the camera photo, fired simultaneously across all spots
    upload_request = build_multipart_request(
        f"{server}/api/v1/sensors/park", config["camera_mac"], image_path
    )
    try:
        if upload_barrier is not None:
            upload_barrier.wait(timeout=60)
        started = time.perf_counter()
        result.upload_status, response_json = send_photo_request(upload_request)
        result.latency_seconds = time.perf_counter() - started
    except Exception as e:
        result.notes = f"photo upload failed: {e}"
        return result

    result.extracted_plate = normalize_plate(response_json.get("plate"))
    result.notes = f"server action={response_json.get('action', '?')} status={response_json.get('status', '?')}"
    return result


def classify_results(spot_results: list[SpotResult]) -> None:
    """Fill in each result's classification, including cross-talk detection."""
    expected_by_spot = {r.spot_id: r.expected_plate for r in spot_results}

    for result in spot_results:
        if result.upload_status not in {200, 202} or (result.notes and "failed" in result.notes):
            result.classification = "ERROR"
            continue

        if result.extracted_plate == result.expected_plate:
            result.classification = "PASS"
            continue

        other_plates = {
            plate for spot, plate in expected_by_spot.items() if spot != result.spot_id
        }
        if result.extracted_plate and result.extracted_plate in other_plates:
            result.classification = "CROSS_TALK"
            offender = next(s for s, p in expected_by_spot.items() if p == result.extracted_plate)
            result.notes += f" | got plate belonging to spot {offender}!"
        elif not result.extracted_plate:
            result.classification = "OCR_MISS"
        else:
            result.classification = "OCR_MISREAD"


def run_round(server: str, spot_ids: list[str], round_number: int, mode: str) -> RoundResult:
    round_result = RoundResult(round_number=round_number, mode=mode)
    images = pick_images(spot_ids, round_number)

    log(f"--- Round {round_number + 1} ({mode}) ---")
    for spot_id in spot_ids:
        log(f"  {spot_id} <- {images[spot_id].name}")

    # Make sure every spot starts FREE so the backend runs OCR fresh.
    with ThreadPoolExecutor(max_workers=len(spot_ids)) as pool:
        list(pool.map(lambda s: free_heartbeat(server, s), spot_ids))
    time.sleep(2.0)

    wall_start = time.perf_counter()

    if mode == "parallel":
        heartbeat_barrier = threading.Barrier(len(spot_ids))
        upload_barrier = threading.Barrier(len(spot_ids))
        with ThreadPoolExecutor(max_workers=len(spot_ids)) as pool:
            futures = [
                pool.submit(run_spot_cycle, server, spot_id, images[spot_id],
                            heartbeat_barrier, upload_barrier)
                for spot_id in spot_ids
            ]
            round_result.spot_results = [f.result() for f in futures]
    else:  # sequential baseline
        for spot_id in spot_ids:
            round_result.spot_results.append(
                run_spot_cycle(server, spot_id, images[spot_id], None, None)
            )

    round_result.wall_clock_seconds = time.perf_counter() - wall_start
    classify_results(round_result.spot_results)

    for result in round_result.spot_results:
        log(f"  {result.spot_id}: [{result.classification}] expected {result.expected_plate or '?'} "
            f"got {result.extracted_plate or '(none)'} in {result.latency_seconds:.2f}s ({result.notes})")
    log(f"  round wall clock: {round_result.wall_clock_seconds:.2f}s")

    # Leave every spot FREE (sessions under 90s log as ABORTED — correct behavior).
    with ThreadPoolExecutor(max_workers=len(spot_ids)) as pool:
        list(pool.map(lambda s: free_heartbeat(server, s), spot_ids))

    return round_result


def format_report(rounds: list[RoundResult], server: str, spot_ids: list[str]) -> tuple[str, bool]:
    all_results = [r for rnd in rounds for r in rnd.spot_results]
    counts = {c: sum(1 for r in all_results if r.classification == c)
              for c in ("PASS", "CROSS_TALK", "OCR_MISS", "OCR_MISREAD", "ERROR")}
    parallelism_ok = counts["CROSS_TALK"] == 0 and counts["ERROR"] == 0

    lines: list[str] = []
    lines.append("=" * 100)
    lines.append("PARKME BACKEND PARALLELISM / SIMULTANEOUS MULTI-SPOT VALIDATION REPORT")
    lines.append("=" * 100)
    lines.append(f"Timestamp        : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Server URL       : {server}")
    lines.append(f"Spots            : {', '.join(spot_ids)}  (simultaneous uploads per round: {len(spot_ids)})")
    lines.append(f"Rounds           : {sum(1 for r in rounds if r.mode == 'parallel')} parallel"
                 + (f" + {sum(1 for r in rounds if r.mode == 'sequential')} sequential baseline"
                    if any(r.mode == "sequential" for r in rounds) else ""))
    lines.append("-" * 100)
    lines.append("SUMMARY:")
    lines.append(f"  PASS         : {counts['PASS']}   (spot got its own plate back)")
    lines.append(f"  CROSS_TALK   : {counts['CROSS_TALK']}   (spot got ANOTHER spot's plate — parallelism bug!)")
    lines.append(f"  OCR_MISS     : {counts['OCR_MISS']}   (no plate read — OCR noise, not a parallelism failure)")
    lines.append(f"  OCR_MISREAD  : {counts['OCR_MISREAD']}   (wrong plate, unrelated to other spots — OCR noise)")
    lines.append(f"  ERROR        : {counts['ERROR']}   (network/HTTP failures)")
    lines.append("")
    lines.append(f"  PARALLELISM VERDICT: {'PASS - no cross-talk, no errors' if parallelism_ok else 'FAIL'}")

    parallel_rounds = [r for r in rounds if r.mode == "parallel"]
    sequential_rounds = [r for r in rounds if r.mode == "sequential"]
    if parallel_rounds:
        avg_parallel = sum(r.wall_clock_seconds for r in parallel_rounds) / len(parallel_rounds)
        lines.append("")
        lines.append(f"  Avg parallel round wall clock   : {avg_parallel:.2f}s "
                     f"for {len(spot_ids)} simultaneous spot arrivals")
    if sequential_rounds:
        avg_sequential = sum(r.wall_clock_seconds for r in sequential_rounds) / len(sequential_rounds)
        lines.append(f"  Avg sequential round wall clock : {avg_sequential:.2f}s (baseline, one spot at a time)")
        if parallel_rounds and avg_parallel > 0:
            lines.append(f"  Speedup from concurrency        : {avg_sequential / avg_parallel:.1f}x")

    lines.append("=" * 100)
    lines.append("")
    lines.append(f"{'Round':<6} | {'Mode':<10} | {'Spot':<4} | {'Image':<16} | {'Expected':<10} | "
                 f"{'Extracted':<10} | {'Latency':<8} | {'Result':<12} | Notes")
    lines.append("-" * 130)
    for rnd in rounds:
        for r in rnd.spot_results:
            lines.append(
                f"{rnd.round_number + 1:<6} | {rnd.mode:<10} | {r.spot_id:<4} | {r.image_name:<16} | "
                f"{r.expected_plate or '?':<10} | {r.extracted_plate or '(none)':<10} | "
                f"{r.latency_seconds:>6.2f}s | [{r.classification}]{'':<{max(0, 10 - len(r.classification))}} | {r.notes}"
            )
    lines.append("-" * 130)
    return "\n".join(lines), parallelism_ok


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate ParkMe backend handling of simultaneous multi-spot image uploads."
    )
    parser.add_argument("--server-url", default=CLOUD_URL,
                        help="Backend base URL (default: the live cloud backend)")
    parser.add_argument("--local", action="store_true", help=f"Shortcut for --server-url {LOCAL_URL}")
    parser.add_argument("--spots", default=",".join(DEFAULT_SPOTS),
                        help="Comma-separated fake spot ids to test (default: all five; C1 is not allowed)")
    parser.add_argument("--rounds", type=int, default=2,
                        help="Number of simultaneous-burst rounds; images rotate each round (default: 2)")
    parser.add_argument("--baseline", action="store_true",
                        help="Also run one sequential round for a wall-clock comparison")
    parser.add_argument("--log-file", default="tests/parallel_test_results.log",
                        help="Where to write the report (default: tests/parallel_test_results.log)")
    args = parser.parse_args()

    server = (LOCAL_URL if args.local else args.server_url).rstrip("/")

    spot_ids = [s.strip().upper() for s in args.spots.split(",") if s.strip()]
    unknown = [s for s in spot_ids if s not in FAKE_SPOTS]
    if unknown:
        sys.exit(f"Unknown or disallowed spot id(s): {unknown}. "
                 f"Allowed fake spots: {list(FAKE_SPOTS)} (C1 is real hardware and is never tested here).")
    if len(spot_ids) < 2:
        sys.exit("Need at least 2 spots to test parallelism.")

    log(f"Testing {len(spot_ids)} spots ({', '.join(spot_ids)}) with SIMULTANEOUS image uploads against {server}")
    log("Each spot uploads a DIFFERENT plate image at the same instant; "
        "each must get its own plate back.")

    rounds: list[RoundResult] = []
    try:
        for round_number in range(args.rounds):
            rounds.append(run_round(server, spot_ids, round_number, "parallel"))
        if args.baseline:
            rounds.append(run_round(server, spot_ids, args.rounds, "sequential"))
    except KeyboardInterrupt:
        log("Interrupted — cleaning up (freeing all tested spots)...")
    finally:
        with ThreadPoolExecutor(max_workers=len(spot_ids)) as pool:
            list(pool.map(lambda s: free_heartbeat(server, s), spot_ids))
        log("All tested spots left FREE.")

    if not rounds or not any(r.spot_results for r in rounds):
        sys.exit("No results collected.")

    report, parallelism_ok = format_report(rounds, server, spot_ids)
    print("\n" + report)

    log_file = Path(args.log_file).resolve()
    log_file.parent.mkdir(parents=True, exist_ok=True)
    log_file.write_text(report + "\n", encoding="utf-8")
    print(f"\nReport saved to: {log_file}")

    sys.exit(0 if parallelism_ok else 1)


if __name__ == "__main__":
    main()
