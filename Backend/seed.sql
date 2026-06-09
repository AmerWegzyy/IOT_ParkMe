INSERT OR IGNORE INTO parking_spots (id, mac_address, category, is_occupied, battery_level, last_seen) VALUES 
('A1', 'AA:BB:CC:DD:EE:01', 'student', 1, 95.5, CURRENT_TIMESTAMP),
('A2', 'AA:BB:CC:DD:EE:02', 'lecturer', 0, 88.0, CURRENT_TIMESTAMP),
('B1', 'AA:BB:CC:DD:EE:03', 'special-needs-driver', 1, 45.2, CURRENT_TIMESTAMP),
('B2', 'AA:BB:CC:DD:EE:04', 'staff', 0, 99.0, CURRENT_TIMESTAMP),
('C1', 'AA:BB:CC:DD:EE:05', 'student', 0, 82.0, CURRENT_TIMESTAMP),
('C2', 'AA:BB:CC:DD:EE:06', 'lecturer', 1, 75.0, CURRENT_TIMESTAMP);

INSERT OR IGNORE INTO users (name, email, role, points) VALUES 
('John Doe', 'student@technion.ac.il', 'student', 10),
('Dr. Smith', 'lecturer@technion.ac.il', 'lecturer', 50),
('Jane Roe', 'jane@technion.ac.il', 'special-needs-driver', 20);

INSERT OR IGNORE INTO vehicles (license_plate, user_id) VALUES 
('1234567', (SELECT id FROM users WHERE email='student@technion.ac.il')),
('9876543', (SELECT id FROM users WHERE email='lecturer@technion.ac.il')),
('1122334', (SELECT id FROM users WHERE email='jane@technion.ac.il'));

INSERT OR IGNORE INTO parking_logs (spot_id, license_plate, user_id, snapshot_role, entry_time, is_violation) VALUES
('A1', '1234567', (SELECT id FROM users WHERE email='student@technion.ac.il'), 'student', CURRENT_TIMESTAMP, 0),
('B1', 'UNIDENTIFIED', NULL, NULL, CURRENT_TIMESTAMP, 1),
('C2', '9876543', (SELECT id FROM users WHERE email='lecturer@technion.ac.il'), 'lecturer', CURRENT_TIMESTAMP, 0);
