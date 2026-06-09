-- Phase 1: SQLite Schema for ParkMe

PRAGMA foreign_keys = ON;

-- USERS TABLE
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('student', 'lecturer', 'staff', 'special-needs-driver', 'admin')),
    points INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- VEHICLES TABLE
-- Relational Integrity: One-to-Many mapping from Users to Vehicles
CREATE TABLE IF NOT EXISTS vehicles (
    license_plate TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- PARKING SPOTS TABLE
-- Hardware Telemetry: Acts as a live state machine for the ESP32 nodes
CREATE TABLE IF NOT EXISTS parking_spots (
    id TEXT PRIMARY KEY, -- e.g., 'A1', 'B2'
    mac_address TEXT UNIQUE NOT NULL, -- To uniquely identify the ESP32 node
    category TEXT NOT NULL CHECK(category IN ('student', 'lecturer', 'staff', 'special-needs-driver')),
    is_occupied BOOLEAN DEFAULT 0,
    battery_level REAL DEFAULT 100.0,
    last_seen DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- PARKING LOGS TABLE
-- Asynchronous Events & History Preservation
CREATE TABLE IF NOT EXISTS parking_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    spot_id TEXT NOT NULL,
    license_plate TEXT, -- Nullable to support 'PENDING' state while waiting for LPR
    user_id INTEGER, -- Nullable if vehicle is unknown/unregistered
    snapshot_role TEXT, -- Historical snapshot of the user's role at time of entry
    entry_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    exit_time DATETIME,
    is_violation BOOLEAN DEFAULT 0,
    FOREIGN KEY (spot_id) REFERENCES parking_spots(id),
    FOREIGN KEY (license_plate) REFERENCES vehicles(license_plate),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- PERFORMANCE INDEXES
CREATE INDEX idx_parking_spots_last_seen ON parking_spots(last_seen);
CREATE INDEX idx_parking_logs_entry ON parking_logs(entry_time);
CREATE INDEX idx_parking_logs_plate ON parking_logs(license_plate);
CREATE INDEX idx_vehicles_user_id ON vehicles(user_id);
