import unittest
from datetime import datetime, timezone
from push_schedule import PACIFIC, event_in_session, within_session


class PushScheduleTests(unittest.TestCase):
    def test_sunday_boundaries_in_summer_and_winter(self):
        for date in ("2026-10-25", "2026-11-08"):
            for clock, expected in (("06:29:00", False), ("16:59:59", False),
                                    ("17:00:00", True), ("19:59:59", True),
                                    ("20:00:00", False)):
                local = datetime.fromisoformat(date + "T" + clock).replace(tzinfo=PACIFIC)
                with self.subTest(date=date, clock=clock):
                    self.assertEqual(within_session(local.astimezone(timezone.utc)), expected)
                    self.assertEqual(event_in_session(local.timestamp() * 1000), expected)

    def test_weekday_windows_unchanged(self):
        for day in range(19, 24):
            for clock, expected in (("06:28:59", False), ("06:29:00", True),
                                    ("08:29:59", True), ("08:30:00", False),
                                    ("16:29:59", False), ("16:30:00", True),
                                    ("19:59:59", True), ("20:00:00", False)):
                with self.subTest(day=day, clock=clock):
                    local = datetime.fromisoformat(f"2026-10-{day}T{clock}").replace(tzinfo=PACIFIC)
                    self.assertEqual(within_session(local), expected)

    def test_saturday_disabled(self):
        self.assertFalse(within_session(datetime(2026, 10, 24, 18, tzinfo=PACIFIC)))


if __name__ == "__main__":
    unittest.main()
