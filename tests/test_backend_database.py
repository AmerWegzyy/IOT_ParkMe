import unittest

from _support import connect_db, create_seeded_database


class DatabaseInitializationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir, self.db_path = create_seeded_database()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_expected_tables_are_created(self):
        with connect_db(self.db_path) as conn:
            table_names = {
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }

        self.assertTrue(
            {"users", "vehicles", "parking_spots", "parking_logs"}.issubset(table_names)
        )

    def test_seed_data_matches_current_schema(self):
        with connect_db(self.db_path) as conn:
            user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            vehicle_count = conn.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0]
            spot_count = conn.execute("SELECT COUNT(*) FROM parking_spots").fetchone()[0]
            log_count = conn.execute("SELECT COUNT(*) FROM parking_logs").fetchone()[0]
            student_user = conn.execute(
                "SELECT role, points FROM users WHERE email = 'student@technion.ac.il'"
            ).fetchone()
            admin_user = conn.execute(
                "SELECT role FROM users WHERE email = 'admin@technion.ac.il'"
            ).fetchone()
            sample_spot = conn.execute(
                "SELECT category, is_occupied FROM parking_spots WHERE id = 'A1'"
            ).fetchone()

        self.assertEqual(user_count, 4)
        self.assertEqual(vehicle_count, 3)
        self.assertEqual(spot_count, 6)
        self.assertEqual(log_count, 3)
        self.assertEqual(student_user["role"], "student")
        self.assertEqual(student_user["points"], 10)
        self.assertEqual(admin_user["role"], "admin")
        self.assertEqual(sample_spot["category"], "student")
        self.assertEqual(sample_spot["is_occupied"], 1)


if __name__ == "__main__":
    unittest.main()
