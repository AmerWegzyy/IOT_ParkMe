import sqlite3
import hashlib

def hash_password(password: str) -> str:
    """Helper function to hash plain text passwords using secure SHA-256."""
    return hashlib.sha256(password.encode()).hexdigest()

def init_database():
    conn = sqlite3.connect("parkme.db")
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")

    print("Re-building database relations with Special Needs accessibility mappings...")

    # 1. Relation: users
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        user_type TEXT NOT NULL,       -- 'student', 'faculty member', 'special needs driver', or 'admin'
        is_looking BOOLEAN DEFAULT 0   -- 0 = Not looking, 1 = Actively looking
    );
    """)

    # 2. Relation: vehicles
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS vehicles (
        license_plate TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
    );
    """)

    # 3. Relation: parking_spots
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS parking_spots (
        spot_id INTEGER PRIMARY KEY,
        spot_type TEXT NOT NULL,       -- 'student', 'faculty member', or 'special needs'
        status INTEGER DEFAULT 0,      -- 0 = Free, 1 = Occupied
        battery_level REAL DEFAULT 100.0,
        last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 4. Relation: parking_logs
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS parking_logs (
        log_id INTEGER PRIMARY KEY AUTOINCREMENT,
        spot_id INTEGER,
        license_plate TEXT,
        action TEXT NOT NULL,          -- 'ENTRY', 'EXIT', 'VIOLATION_ATTEMPT'
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (spot_id) REFERENCES parking_spots(spot_id) ON DELETE SET NULL,
        FOREIGN KEY (license_plate) REFERENCES vehicles(license_plate) ON DELETE SET NULL
    );
    """)

    print("Seeding database with updated Technion roles...")
    default_hash = hash_password("password123")

    # Seed Users (Including our new Special Needs profile)
    cursor.execute("INSERT OR IGNORE INTO users (user_id, name, username, password_hash, user_type, is_looking) VALUES (1, 'Amer', 'amer_s', ?, 'student', 1);", (default_hash,))
    cursor.execute("INSERT OR IGNORE INTO users (user_id, name, username, password_hash, user_type, is_looking) VALUES (2, 'Majd', 'majd_p', ?, 'student', 0);", (default_hash,))
    cursor.execute("INSERT OR IGNORE INTO users (user_id, name, username, password_hash, user_type, is_looking) VALUES (3, 'Professor Isaac', 'isaac_prof', ?, 'faculty member', 0);", (default_hash,))
    cursor.execute("INSERT OR IGNORE INTO users (user_id, name, username, password_hash, user_type, is_looking) VALUES (4, 'Technion Security', 'admin', ?, 'admin', 0);", (default_hash,))
    cursor.execute("INSERT OR IGNORE INTO users (user_id, name, username, password_hash, user_type, is_looking) VALUES (5, 'Youssef (Accessible)', 'youssef_acc', ?, 'special needs driver', 1);", (default_hash,))

    # Seed Vehicles
    cursor.execute("INSERT OR IGNORE INTO vehicles (license_plate, user_id) VALUES ('123-45-678', 1);") # Amer
    cursor.execute("INSERT OR IGNORE INTO vehicles (license_plate, user_id) VALUES ('987-65-432', 2);") # Majd
    cursor.execute("INSERT OR IGNORE INTO vehicles (license_plate, user_id) VALUES ('555-55-555', 3);") # Professor Isaac
    cursor.execute("INSERT OR IGNORE INTO vehicles (license_plate, user_id) VALUES ('777-11-777', 5);") # Youssef

    # Seed Parking Spots (Adding a dedicated accessible bay)
    cursor.execute("INSERT OR IGNORE INTO parking_spots (spot_id, spot_type, status, battery_level) VALUES (101, 'student', 0, 94.2);")
    cursor.execute("INSERT OR IGNORE INTO parking_spots (spot_id, spot_type, status, battery_level) VALUES (102, 'student', 1, 42.0);")
    cursor.execute("INSERT OR IGNORE INTO parking_spots (spot_id, spot_type, status, battery_level) VALUES (201, 'faculty member', 0, 100.0);")
    cursor.execute("INSERT OR IGNORE INTO parking_spots (spot_id, spot_type, status, battery_level) VALUES (301, 'special needs', 0, 88.5);")

    # Seed initial test logs to showcase historical tracking architecture
    cursor.execute("INSERT OR IGNORE INTO parking_logs (log_id, spot_id, license_plate, action) VALUES (1, 201, '123-45-678', 'VIOLATION_ATTEMPT');") # Amer trying to park in faculty spot
    cursor.execute("INSERT OR IGNORE INTO parking_logs (log_id, spot_id, license_plate, action) VALUES (2, 301, '777-11-777', 'ENTRY');")             # Youssef successfully entering accessible spot

    conn.commit()
    conn.close()
    print("Database built cleanly! Run 'python3 main.py' to launch the service gateway.")

if __name__ == "__main__":
    init_database()