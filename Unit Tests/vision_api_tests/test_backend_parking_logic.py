import unittest
from datetime import datetime, timedelta, timezone

from Backend.parking_logic import should_preserve_recent_active_log, seconds_since


class ParkingLogicTests(unittest.TestCase):
    def test_seconds_since_handles_timezone_aware_timestamps(self):
        jerusalem_tz = timezone(timedelta(hours=3))
        now = datetime(2026, 6, 23, 12, 0, tzinfo=jerusalem_tz)
        reference = datetime(2026, 6, 23, 8, 59, 50, tzinfo=timezone.utc)

        self.assertEqual(seconds_since(reference, now), 10)

    def test_preserves_recent_camera_first_log_when_it_is_newer_than_last_seen(self):
        jerusalem_tz = timezone(timedelta(hours=3))
        now = datetime(2026, 6, 23, 12, 0, tzinfo=jerusalem_tz)
        entry_time = now - timedelta(seconds=4)
        last_seen = now - timedelta(seconds=15)

        self.assertTrue(
            should_preserve_recent_active_log(
                entry_time=entry_time,
                license_plate="1234567",
                spot_last_seen=last_seen,
                now=now,
                preserve_window_seconds=20,
                non_preservable_plates={"RESOLVED", "REJECTED", "MANUAL_ACCEPTED", "ABORTED"},
            )
        )

    def test_rejects_old_log_when_spot_was_seen_after_the_log_started(self):
        jerusalem_tz = timezone(timedelta(hours=3))
        now = datetime(2026, 6, 23, 12, 0, tzinfo=jerusalem_tz)
        entry_time = now - timedelta(seconds=8)
        last_seen = now - timedelta(seconds=3)

        self.assertFalse(
            should_preserve_recent_active_log(
                entry_time=entry_time,
                license_plate="1234567",
                spot_last_seen=last_seen,
                now=now,
                preserve_window_seconds=20,
                non_preservable_plates={"RESOLVED", "REJECTED", "MANUAL_ACCEPTED", "ABORTED"},
            )
        )

    def test_rejects_terminal_marker_logs_even_if_they_are_recent(self):
        jerusalem_tz = timezone(timedelta(hours=3))
        now = datetime(2026, 6, 23, 12, 0, tzinfo=jerusalem_tz)
        entry_time = now - timedelta(seconds=5)
        last_seen = now - timedelta(seconds=15)

        self.assertFalse(
            should_preserve_recent_active_log(
                entry_time=entry_time,
                license_plate="REJECTED",
                spot_last_seen=last_seen,
                now=now,
                preserve_window_seconds=20,
                non_preservable_plates={"RESOLVED", "REJECTED", "MANUAL_ACCEPTED", "ABORTED"},
            )
        )


if __name__ == "__main__":
    unittest.main()
