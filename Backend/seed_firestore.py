"""
seed_firestore.py
Seeds the Firestore database with test data for the ParkMe project.

Usage:
    Ensure GOOGLE_APPLICATION_CREDENTIALS is set (or serviceAccountKey.json is in cwd).
    Then run:  python seed_firestore.py
"""

import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timezone
from dotenv import load_dotenv
load_dotenv()


def get_firestore_client() -> firestore.firestore.Client:
    """Initialize Firebase Admin SDK and return a Firestore client."""
    if not firebase_admin._apps:
        cred = credentials.ApplicationDefault()
        firebase_admin.initialize_app(cred)
    return firestore.client()


def seed_parking_spots(db: firestore.firestore.Client) -> None:
    """Seed the parking_spots collection."""
    print("⏳ Seeding parking_spots …")
    spots = [
        {"id": "A1", "mac_address": "AA:BB:CC:DD:EE:01", "category": "student",
         "is_occupied": True,  "battery_level": 95.5},
        {"id": "A2", "mac_address": "AA:BB:CC:DD:EE:02", "category": "lecturer",
         "is_occupied": False, "battery_level": 88.0},
        {"id": "B1", "mac_address": "AA:BB:CC:DD:EE:03", "category": "special-needs-driver",
         "is_occupied": True,  "battery_level": 45.2},
        {"id": "B2", "mac_address": "AA:BB:CC:DD:EE:04", "category": "staff",
         "is_occupied": False, "battery_level": 99.0},
        {"id": "C1", "mac_address": "AA:BB:CC:DD:EE:05", "category": "student",
         "is_occupied": False, "battery_level": 82.0},
        {"id": "C2", "mac_address": "AA:BB:CC:DD:EE:06", "category": "lecturer",
         "is_occupied": True,  "battery_level": 75.0},
    ]
    for spot in spots:
        doc_id = spot["id"]
        spot["last_seen"] = datetime.now(timezone.utc)
        db.collection("parking_spots").document(doc_id).set(spot)
        print(f"  ✅ parking_spots/{doc_id}")


def seed_users(db: firestore.firestore.Client) -> dict[str, str]:
    """Seed the users collection. Returns a mapping of email -> document ID."""
    print("⏳ Seeding users …")
    users = [
        {"name": "Admin User", "email": "admin@technion.ac.il",
         "role": "admin",                 "points": 999},
        {"name": "John Doe",  "email": "student@technion.ac.il",
         "role": "student",               "points": 10},
        {"name": "Dr. Smith", "email": "lecturer@technion.ac.il",
         "role": "lecturer",              "points": 50},
        {"name": "Jane Roe",  "email": "jane@technion.ac.il",
         "role": "special-needs-driver",  "points": 20},
    ]
    email_to_id: dict[str, str] = {}
    for user in users:
        user["created_at"] = datetime.now(timezone.utc)
        doc_id = user["email"]
        db.collection("users").document(doc_id).set(user)
        email_to_id[user["email"]] = doc_id
        print(f"  ✅ users/{doc_id}  ({user['name']})")
    return email_to_id


def seed_vehicles(db: firestore.firestore.Client, email_to_id: dict[str, str]) -> None:
    """Seed the vehicles collection (document ID = license_plate)."""
    print("⏳ Seeding vehicles …")
    vehicles = [
        {"license_plate": "1234567", "user_id": email_to_id["student@technion.ac.il"]},
        {"license_plate": "9876543", "user_id": email_to_id["lecturer@technion.ac.il"]},
        {"license_plate": "1122334", "user_id": email_to_id["jane@technion.ac.il"]},
    ]
    for vehicle in vehicles:
        doc_id = vehicle["license_plate"]
        vehicle["created_at"] = datetime.now(timezone.utc)
        db.collection("vehicles").document(doc_id).set(vehicle)
        print(f"  ✅ vehicles/{doc_id}")


def seed_parking_logs(db: firestore.firestore.Client, email_to_id: dict[str, str]) -> None:
    """Seed the parking_logs collection."""
    print("⏳ Seeding parking_logs …")
    logs = [
        {
            "spot_id": "A1",
            "license_plate": "1234567",
            "user_id": email_to_id["student@technion.ac.il"],
            "snapshot_role": "student",
            "entry_time": datetime.now(timezone.utc),
            "exit_time": None,
            "is_violation": False,
        },
        {
            "spot_id": "B1",
            "license_plate": "UNIDENTIFIED",
            "user_id": None,
            "snapshot_role": None,
            "entry_time": datetime.now(timezone.utc),
            "exit_time": None,
            "is_violation": True,
        },
        {
            "spot_id": "C2",
            "license_plate": "9876543",
            "user_id": email_to_id["lecturer@technion.ac.il"],
            "snapshot_role": "lecturer",
            "entry_time": datetime.now(timezone.utc),
            "exit_time": None,
            "is_violation": False,
        },
    ]
    for log in logs:
        _, doc_ref = db.collection("parking_logs").add(log)
        print(f"  ✅ parking_logs/{doc_ref.id}  (spot {log['spot_id']})")


def main() -> None:
    print("🚀 ParkMe Firestore Seeder")
    print("=" * 40)
    db = get_firestore_client()

    seed_parking_spots(db)
    email_to_id = seed_users(db)
    seed_vehicles(db, email_to_id)
    seed_parking_logs(db, email_to_id)

    print("=" * 40)
    print("🎉 Seeding complete!")


if __name__ == "__main__":
    main()
