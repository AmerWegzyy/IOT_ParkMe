#!/usr/bin/env python3
"""
test_lpr_pipeline.py — ParkMe License Plate Recognition (LPR) Pipeline Validation

PURPOSE:
    This script tests the end-to-end license plate recognition pipeline of the ParkMe backend.
    It simulates an ESP32-CAM camera node uploading images to the server's POST /api/v1/sensors/park
    endpoint. The backend processes each image using Google Cloud Vision OCR, extracts an Israeli
    license plate (7-8 digits), and returns the extracted plate in the JSON response.

HOW IT WORKS:
    1. Scans the target directory (`tests/test_pics/` by default) for image files (.jpg, .png, .webp).
    2. Derives the expected license plate number from the filename stem (e.g., "1234590.jpg" -> "1234590").
    3. Sends each image via multipart/form-data POST request to `/api/v1/sensors/park` along with a
       seeded camera MAC address (`FF:EE:DD:CC:BB:01` by default).
    4. Compares the server's extracted plate against the expected plate (normalized to digits).
    5. Records PASS/FAIL per image, prints a formatted summary table to stdout, and writes a log file.

USAGE:
    # Run against local server (http://127.0.0.1:8000) using default test pictures directory:
    python3 tests/test_lpr_pipeline.py

    # Run against a custom server URL or custom pictures directory:
    python3 tests/test_lpr_pipeline.py --server-url http://127.0.0.1:8000 --pics-dir tests/test_pics

INTERPRETING RESULTS:
    - [PASS]: The extracted plate exactly matches the expected plate derived from the filename.
    - [FAIL]: The extracted plate differs from the expected plate, or OCR failed to extract a plate.
    - [ERROR]: A network error, server error, or invalid response occurred during processing.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


@dataclass
class TestResult:
    filename: str
    expected_plate: str
    extracted_plate: str
    status: str  # "PASS", "FAIL", or "ERROR"
    notes: str


def normalize_plate(raw: Optional[str]) -> str:
    """Strip spaces, dashes, and non-digit characters from a plate string."""
    if not raw:
        return ""
    return "".join(ch for ch in str(raw) if ch.isdigit())


def post_multipart_image(
    url: str, camera_mac: str, file_path: Path, timeout_seconds: int = 15
) -> Tuple[int, dict, str]:
    """
    Send a multipart/form-data POST request using standard library urllib.
    Returns (status_code, parsed_json_dict, raw_response_text).
    """
    boundary = f"----ParkMeBoundary{uuid.uuid4().hex}"
    filename = file_path.name

    with open(file_path, "rb") as f:
        file_bytes = f.read()

    # Build multipart body
    body = bytearray()

    # Form field: camera_mac
    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(
        f'Content-Disposition: form-data; name="camera_mac"\r\n\r\n{camera_mac}\r\n'.encode("utf-8")
    )

    # Form field: file
    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode("utf-8")
    )
    body.extend(b"Content-Type: image/jpeg\r\n\r\n")
    body.extend(file_bytes)
    body.extend(b"\r\n")

    # End boundary
    body.extend(f"--{boundary}--\r\n".encode("utf-8"))

    req = Request(url, data=bytes(body), method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    req.add_header("Content-Length", str(len(body)))

    try:
        with urlopen(req, timeout=timeout_seconds) as resp:
            status_code = resp.status
            raw_text = resp.read().decode("utf-8", errors="replace")
            try:
                data = json.loads(raw_text)
            except Exception:
                data = {}
            return status_code, data, raw_text
    except HTTPError as e:
        raw_text = e.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(raw_text)
        except Exception:
            data = {}
        return e.code, data, raw_text
    except URLError as e:
        raise RuntimeError(f"Server unreachable ({e.reason})")


def reset_spot_session(server_url: str, sensor_mac: str, timeout_seconds: int = 5) -> None:
    """
    Send a heartbeat with is_occupied=False to close any existing parking log
    so the backend runs OCR afresh on the next camera upload.
    """
    heartbeat_url = f"{server_url.rstrip('/')}/api/v1/sensors/heartbeat"
    payload = json.dumps({
        "mac_address": sensor_mac,
        "is_occupied": False,
        "battery_level": 100.0
    }).encode("utf-8")

    req = Request(heartbeat_url, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urlopen(req, timeout=timeout_seconds):
            pass
    except Exception:
        pass


def run_pipeline_tests(
    server_url: str,
    pics_dir: Path,
    camera_mac: str,
    sensor_mac: str = "AA:BB:CC:DD:EE:01",
    timeout_seconds: int = 15,
) -> list[TestResult]:
    """Scan images in pics_dir and test each against the backend LPR endpoint."""
    endpoint_url = f"{server_url.rstrip('/')}/api/v1/sensors/park"
    results: list[TestResult] = []

    image_files = sorted(
        [
            p
            for p in pics_dir.iterdir()
            if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
        ]
    )

    if not image_files:
        raise FileNotFoundError(f"No image files found in directory: {pics_dir}")

    for img_path in image_files:
        reset_spot_session(server_url, sensor_mac)
        expected_raw = img_path.stem
        expected_plate = normalize_plate(expected_raw)

        if not expected_plate:
            results.append(
                TestResult(
                    filename=img_path.name,
                    expected_plate=expected_raw,
                    extracted_plate="N/A",
                    status="ERROR",
                    notes="Filename does not encode numeric plate digits",
                )
            )
            continue

        try:
            status_code, resp_json, raw_text = post_multipart_image(
                endpoint_url, camera_mac, img_path, timeout_seconds=timeout_seconds
            )

            if status_code not in {200, 202}:
                err_msg = resp_json.get("detail") or resp_json.get("message") or f"HTTP {status_code}"
                results.append(
                    TestResult(
                        filename=img_path.name,
                        expected_plate=expected_plate,
                        extracted_plate="N/A",
                        status="ERROR",
                        notes=f"Server returned HTTP {status_code}: {err_msg}",
                    )
                )
                continue

            extracted_raw = resp_json.get("plate")
            extracted_plate = normalize_plate(extracted_raw)

            if not extracted_plate:
                # OCR found no valid plate or backend marked manual_review
                server_status = resp_json.get("status", "unknown")
                results.append(
                    TestResult(
                        filename=img_path.name,
                        expected_plate=expected_plate,
                        extracted_plate="(none)",
                        status="FAIL",
                        notes=f"No plate extracted by Vision API (status: {server_status})",
                    )
                )
            elif extracted_plate == expected_plate:
                results.append(
                    TestResult(
                        filename=img_path.name,
                        expected_plate=expected_plate,
                        extracted_plate=extracted_plate,
                        status="PASS",
                        notes="Exact match",
                    )
                )
            else:
                results.append(
                    TestResult(
                        filename=img_path.name,
                        expected_plate=expected_plate,
                        extracted_plate=extracted_plate,
                        status="FAIL",
                        notes=f"Mismatch (expected {expected_plate}, got {extracted_plate})",
                    )
                )

        except Exception as exc:
            results.append(
                TestResult(
                    filename=img_path.name,
                    expected_plate=expected_plate,
                    extracted_plate="N/A",
                    status="ERROR",
                    notes=str(exc),
                )
            )

    return results


def format_report(results: list[TestResult], server_url: str, pics_dir: Path) -> str:
    """Format a human-readable summary and detailed results table."""
    total = len(results)
    pass_count = sum(1 for r in results if r.status == "PASS")
    fail_count = sum(1 for r in results if r.status == "FAIL")
    error_count = sum(1 for r in results if r.status == "ERROR")
    pass_rate = (pass_count / total * 100.0) if total > 0 else 0.0

    lines: list[str] = []
    lines.append("=" * 86)
    lines.append("PARKME LICENSE PLATE RECOGNITION (LPR) PIPELINE VALIDATION REPORT")
    lines.append("=" * 86)
    lines.append(f"Timestamp    : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Server URL   : {server_url}")
    lines.append(f"Test Images  : {pics_dir}")
    lines.append("-" * 86)
    lines.append("SUMMARY STATS:")
    lines.append(f"  Total Images Tested : {total}")
    lines.append(f"  PASS Count          : {pass_count}")
    lines.append(f"  FAIL Count          : {fail_count}")
    lines.append(f"  ERROR Count         : {error_count}")
    lines.append(f"  Pass Rate           : {pass_rate:.1f}%")
    lines.append("=" * 86)
    lines.append("")
    lines.append(
        f"{'Filename':<18} | {'Expected':<10} | {'Extracted':<10} | {'Result':<8} | {'Notes'}"
    )
    lines.append("-" * 86)

    for r in results:
        status_badge = f"[{r.status}]"
        lines.append(
            f"{r.filename:<18} | {r.expected_plate:<10} | {r.extracted_plate:<10} | {status_badge:<8} | {r.notes}"
        )

    lines.append("-" * 86)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Validate ParkMe backend LPR pipeline against test image folder."
    )
    parser.add_argument(
        "--server-url",
        default="http://127.0.0.1:8000",
        help="Base URL of the ParkMe FastAPI server (default: http://127.0.0.1:8000)",
    )
    parser.add_argument(
        "--pics-dir",
        default="tests/test_pics",
        help="Directory containing test license plate images (default: tests/test_pics)",
    )
    parser.add_argument(
        "--camera-mac",
        default="FF:EE:DD:CC:BB:01",
        help="Seeded camera MAC address to authenticate spot upload (default: FF:EE:DD:CC:BB:01 for spot A1)",
    )
    parser.add_argument(
        "--sensor-mac",
        default="AA:BB:CC:DD:EE:01",
        help="Seeded sensor MAC address to clear spot occupancy between tests (default: AA:BB:CC:DD:EE:01 for spot A1)",
    )
    parser.add_argument(
        "--log-file",
        default="tests/lpr_test_results.log",
        help="Path where formatted results log file should be written (default: tests/lpr_test_results.log)",
    )

    args = parser.parse_args()

    pics_dir = Path(args.pics_dir).resolve()
    log_file = Path(args.log_file).resolve()

    if not pics_dir.is_dir():
        print(f"ERROR: Pictures directory '{pics_dir}' does not exist.", file=sys.stderr)
        sys.exit(1)

    print(f"Starting LPR pipeline tests against {args.server_url} ...")
    print(f"Scanning images in: {pics_dir}")

    try:
        results = run_pipeline_tests(args.server_url, pics_dir, args.camera_mac, args.sensor_mac)
    except Exception as e:
        print(f"ERROR: Failed to execute pipeline tests: {e}", file=sys.stderr)
        sys.exit(1)

    report = format_report(results, args.server_url, pics_dir)
    print("\n" + report)

    log_file.parent.mkdir(parents=True, exist_ok=True)
    with open(log_file, "w", encoding="utf-8") as f:
        f.write(report + "\n")

    print(f"\nReport saved to: {log_file}")


if __name__ == "__main__":
    main()
