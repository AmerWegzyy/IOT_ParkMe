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


def delete_collection(db: firestore.firestore.Client, coll_name: str, batch_size: int = 500):
    """Deletes all documents in a collection to prevent duplicates."""
    print(f"🧹 Wiping existing '{coll_name}' collection...")
    docs = db.collection(coll_name).limit(batch_size).stream()
    deleted = 0
    for doc in docs:
        doc.reference.delete()
        deleted += 1
    if deleted >= batch_size:
        return delete_collection(db, coll_name, batch_size)
    print(f"  ✨ Wiped {coll_name} completely.")


def seed_parking_spots(db: firestore.firestore.Client) -> None:
    """Seed the parking_spots collection."""
    delete_collection(db, "parking_spots")
    print("⏳ Seeding parking_spots …")
    spots = [
        {"id": "A1", "sensor_mac": "AA:BB:CC:DD:EE:01", "camera_mac": "FF:EE:DD:CC:BB:01", "category": "student",
         "is_occupied": True,  "battery_level": 95.5},
        {"id": "A2", "sensor_mac": "AA:BB:CC:DD:EE:02", "camera_mac": "FF:EE:DD:CC:BB:02", "category": "lecturer",
         "is_occupied": False, "battery_level": 88.0},
        {"id": "B1", "sensor_mac": "AA:BB:CC:DD:EE:03", "camera_mac": "FF:EE:DD:CC:BB:03", "category": "special-needs-driver",
         "is_occupied": True,  "battery_level": 45.2},
        {"id": "B2", "sensor_mac": "AA:BB:CC:DD:EE:04", "camera_mac": "FF:EE:DD:CC:BB:04", "category": "staff",
         "is_occupied": False, "battery_level": 99.0},
        {"id": "C1", "sensor_mac": "AA:BB:CC:DD:EE:05", "camera_mac": "FF:EE:DD:CC:BB:05", "category": "student",
         "is_occupied": False, "battery_level": 82.0},
        {"id": "C2", "sensor_mac": "AA:BB:CC:DD:EE:06", "camera_mac": "FF:EE:DD:CC:BB:06", "category": "lecturer",
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
         "role": "admin"},
        {"name": "John Doe",  "email": "student@technion.ac.il",
         "role": "student"},
        {"name": "Dr. Smith", "email": "lecturer@technion.ac.il",
         "role": "lecturer"},
        {"name": "Jane Roe",  "email": "jane@technion.ac.il",
         "role": "special-needs-driver"},
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


def main() -> None:
    print("🚀 ParkMe Firestore Seeder")
    print("=" * 40)
    db = get_firestore_client()

    # Clean up deprecated collection
    delete_collection(db, "camera_commands")

    seed_parking_spots(db)
    email_to_id = seed_users(db)
    seed_vehicles(db, email_to_id)
    # Note: intentionally skipping parking_logs to preserve history


    print("=" * 40)
    print("🎉 Seeding complete!")


if __name__ == "__main__":
    main()
