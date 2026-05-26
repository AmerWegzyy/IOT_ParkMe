import sqlite3
import hashlib

DB_FILE = "parkme.db"

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def init_database():
    print(f"[DATABASE] Opening connection to local database file: '{DB_FILE}'")
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Enable foreign key enforcement in SQLite
    cursor.execute("PRAGMA foreign_keys = ON;")

    print("[DATABASE] Building tables with strict One-to-One constraints...")

    # 1. Users Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        user_type TEXT NOT NULL,
        is_looking BOOLEAN DEFAULT 0
    );
    """)

    # 2. Vehicles Table (Enforcing Exactly One Plate Per User)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS vehicles (
        license_plate TEXT PRIMARY KEY,
        -- Added UNIQUE below to strictly enforce the One-to-One relationship
        user_id INTEGER NOT NULL UNIQUE, 
        FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
    );
    """)

    # 3. Parking Spots Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS parking_spots (
        spot_id INTEGER PRIMARY KEY,
        spot_type TEXT NOT NULL,
        status INTEGER DEFAULT 0,
        battery_level REAL DEFAULT 100.0,
        last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 4. Incident & Activity Logs Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS parking_logs (
        log_id INTEGER PRIMARY KEY AUTOINCREMENT,
        spot_id INTEGER,
        license_plate TEXT,
        action TEXT NOT NULL,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (spot_id) REFERENCES parking_spots(spot_id) ON DELETE SET NULL,
        FOREIGN KEY (license_plate) REFERENCES vehicles(license_plate) ON DELETE SET NULL
    );
    """)

    print("[DATABASE] Seeding authorized Technion profiles into matrices...")
    default_hash = hash_password("password123")

    # Insert Default Users
    cursor.execute("""
    INSERT OR IGNORE INTO users (user_id, name, username, password_hash, user_type, is_looking) 
    VALUES 
        (1, 'Amer', 'amer_s', ?, 'student', 1),
        (2, 'Majd', 'majd_p', ?, 'student', 0),
        (3, 'Professor Isaac', 'isaac_prof', ?, 'faculty member', 0),
        (4, 'Technion Security', 'admin', ?, 'admin', 0),
        (5, 'Youssef (Accessible)', 'youssef_acc', ?, 'special needs driver', 1)
    """, (default_hash, default_hash, default_hash, default_hash, default_hash))

    # Insert Vehicles (Each user_id appears exactly once)
    cursor.execute("""
    INSERT OR IGNORE INTO vehicles (license_plate, user_id) 
    VALUES 
        ('123-45-678', 1), 
        ('987-65-432', 2), 
        ('555-55-555', 3), 
        ('777-11-777', 5)
    """)

    # Insert Physical Parking Nodes
    cursor.execute("""
    INSERT OR IGNORE INTO parking_spots (spot_id, spot_type, status, battery_level) 
    VALUES 
        (101, 'student', 0, 94.2),
        (102, 'student', 1, 42.0),
        (201, 'faculty member', 0, 100.0),
        (301, 'special needs', 0, 88.5)
    """)

    conn.commit()
    cursor.close()
    conn.close()
    print("[DATABASE] Initialization completed successfully! parkme.db is ready.")

if __name__ == "__main__":
    init_database()