#!/usr/bin/env python3
"""Seed the presentation users/vehicles matching the demo plate photos.

The photos in the presenter's presentation_pics folder are named
<plate>_<name>_<role>.jpg; this script makes Firestore agree with them so
each photo produces the right WELCOME/DENIED verdict live on stage.

Idempotent and safe: touches ONLY these five users and five vehicle docs
(overwriting older test-user mappings for the same plates). Never touches
parking_spots, logs, or the four dashboard login accounts.

Run from Backend/:  ./.venv/Scripts/python.exe seed_presentation_users.py
"""

from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

_backend_dir = Path(__file__).resolve().parent
for name in (".env", "env"):
    candidate = _backend_dir / name
    if candidate.exists():
        load_dotenv(candidate)

import firebase_admin
from firebase_admin import credentials, firestore

# plate -> (display name, email, role); matches presentation_pics filenames.
PRESENTATION_PEOPLE = [
    {"plate": "1234590",  "name": "George",  "email": "george.driver@technion.ac.il",  "role": "student"},
    {"plate": "1762438",  "name": "Aamer",   "email": "aamer.driver@technion.ac.il",   "role": "lecturer"},
    {"plate": "1777765",  "name": "Jade",    "email": "jade.driver@technion.ac.il",    "role": "special-needs-driver"},
    {"plate": "26205301", "name": "Ameer",   "email": "ameer.driver@technion.ac.il",   "role": "student"},
    {"plate": "9044970",  "name": "Michael", "email": "michael.driver@technion.ac.il", "role": "student"},
]


def main() -> None:
    firebase_admin.initialize_app(credentials.ApplicationDefault())
    db = firestore.client()
    now = datetime.now(timezone.utc)

    for person in PRESENTATION_PEOPLE:
        db.collection("users").document(person["email"]).set({
            "name": person["name"],
            "email": person["email"],
            "role": person["role"],
            "created_at": now,
        })
        db.collection("vehicles").document(person["plate"]).set({
            "license_plate": person["plate"],
            "user_id": person["email"],
            "created_at": now,
        })
        print(f"  users/{person['email']} ({person['name']}, {person['role']})  <-  vehicles/{person['plate']}")

    print()
    print("Expected verdicts on spot C1 (category: student):")
    for person in PRESENTATION_PEOPLE:
        ok = person["role"] in ("student", "admin")
        verdict = f"WELCOME {person['name']}" if ok else "ACCESS DENIED (+ violation log)"
        print(f"  {person['plate']:<9} {person['name']:<8} {person['role']:<20} -> {verdict}")
    print("  (Jade is WELCOME on the special-needs spot B1 — visible via the simulator.)")


if __name__ == "__main__":
    main()
