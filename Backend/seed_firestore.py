"""
seed_firestore.py
Seeds the Firestore database with test data for the ParkMe project.

Usage:
    Ensure GOOGLE_APPLICATION_CREDENTIALS is set (or serviceAccountKey.json is in cwd).
    Then run:  python seed_firestore.py
"""

import firebase_admin
from firebase_admin import credentials, firestore, auth
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

# Load Backend/.env or Backend/env (same lookup main.py uses), regardless of cwd.
_backend_dir = Path(__file__).resolve().parent
for _env_name in (".env", "env"):
    _env_path = _backend_dir / _env_name
    if _env_path.exists():
        load_dotenv(_env_path)
        break


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


def seed_additional_test_users_and_vehicles(db: firestore.firestore.Client) -> None:
    """Add up to 5 test users and vehicles idempotently based on tests/test_pics/."""
    print("⏳ Seeding additional test users & vehicles (idempotent) …")
    test_pics_dir = _backend_dir.parent / "tests" / "test_pics"
    extracted_plates = []
    if test_pics_dir.exists():
        extracted_plates = sorted(
            p.stem for p in test_pics_dir.iterdir() if p.is_file() and p.stem.isdigit()
        )
    fallback_plates = ["1234590", "12823303", "1762438", "1777765", "26205301"]
    plates = extracted_plates if len(extracted_plates) >= 5 else fallback_plates

    new_test_users = [
        {"name": "Test Student 1", "email": "test.student1@technion.ac.il", "role": "student", "plate": plates[0]},
        {"name": "Test Lecturer 1", "email": "test.lecturer1@technion.ac.il", "role": "lecturer", "plate": plates[1]},
        {"name": "Test Staff 1", "email": "test.staff1@technion.ac.il", "role": "staff", "plate": plates[2]},
        {"name": "Test Special Needs 1", "email": "test.special1@technion.ac.il", "role": "special-needs-driver", "plate": plates[3]},
        {"name": "Test Student 2", "email": "test.student2@technion.ac.il", "role": "student", "plate": plates[4]},
    ]

    for item in new_test_users:
        user_email = item["email"]
        user_doc_ref = db.collection("users").document(user_email)
        if not user_doc_ref.get().exists:
            user_data = {
                "name": item["name"],
                "email": user_email,
                "role": item["role"],
                "created_at": datetime.now(timezone.utc),
            }
            user_doc_ref.set(user_data)
            print(f"  ✅ users/{user_email} ({item['name']} - {item['role']})")
        else:
            print(f"  ℹ️ users/{user_email} already exists (skipping)")

        plate_num = item["plate"]
        veh_doc_ref = db.collection("vehicles").document(plate_num)
        if not veh_doc_ref.get().exists:
            veh_data = {
                "license_plate": plate_num,
                "user_id": user_email,
                "created_at": datetime.now(timezone.utc),
            }
            veh_doc_ref.set(veh_data)
            print(f"  ✅ vehicles/{plate_num} -> {user_email}")
        else:
            print(f"  ℹ️ vehicles/{plate_num} already exists (skipping)")

        # Create Firebase Auth account if not exists
        try:
            auth.create_user(
                email=user_email,
                password="password123",
                display_name=item["name"],
            )
            print(f"  ✅ Auth user created: {user_email}")
        except Exception as e:
            if "ALREADY_EXISTS" in str(e) or "already exists" in str(e).lower() or "EmailAlreadyExists" in type(e).__name__:
                print(f"  ℹ️ Auth user {user_email} already exists (skipping)")
            else:
                print(f"  ⚠️ Could not create auth user {user_email}: {e}")


def main() -> None:
    print("🚀 ParkMe Firestore Seeder")
    print("=" * 40)
    db = get_firestore_client()

    # Clean up deprecated collection
    delete_collection(db, "camera_commands")

    seed_parking_spots(db)
    email_to_id = seed_users(db)
    seed_vehicles(db, email_to_id)
    seed_additional_test_users_and_vehicles(db)
    # Note: intentionally skipping parking_logs to preserve history


    print("=" * 40)
    print("🎉 Seeding complete!")


if __name__ == "__main__":
    main()
