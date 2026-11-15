import unittest
from datetime import datetime, timezone

from five_minute_watchdog import plan, record

UTC = timezone.utc
START = "2026-11-15T00:00:00Z"
MODE = {"schema_version": 1, "mode": "v2", "first_slot_utc": START}


class WatchdogTests(unittest.TestCase):
    def test_first_check_catches_whole_slots_even_without_any_dispatch(self):
        batch = plan(MODE, None, datetime(2026, 11, 15, 0, 31, tzinfo=UTC))
        self.assertEqual((batch["start"], batch["end"]), (START, "2026-11-15T00:15:00Z"))
        result = record(batch, {START: ["BTC", "ETH"]}, ("BTC", "ETH"))
        self.assertEqual(result["expected_slots"], 4)
        self.assertEqual(result["missing_symbols"], 2)

    def test_watermark_does_not_skip_after_long_outage(self):
        batch = plan(MODE, None, datetime(2026, 11, 18, tzinfo=UTC))
        self.assertGreater(batch["remaining_slots"], 0)
        self.assertEqual(batch["end"], "2026-11-15T23:55:00Z")
        later = plan(MODE, batch["next_state"], datetime(2026, 11, 18, tzinfo=UTC))
        self.assertEqual(later["start"], "2026-11-16T00:00:00Z")

    def test_rejects_bad_state_future_slot_and_unexpected_gap(self):
        with self.assertRaisesRegex(ValueError, "outside expected range"):
            plan(MODE, {"version": 1, "first_slot_utc": START,
                        "last_audited_slot_utc": "2026-11-16T00:00:00Z"},
                 datetime(2026, 11, 15, 1, tzinfo=UTC))
        batch = plan(MODE, None, datetime(2026, 11, 15, 0, 31, tzinfo=UTC))
        with self.assertRaisesRegex(ValueError, "invalid"):
            record(batch, {"2026-11-14T23:55:00Z": ["BTC"]}, ("BTC",))

    def test_legacy_skips_without_inventing_a_start(self):
        self.assertIsNone(plan({"schema_version": 1, "mode": "legacy"}, None,
                               datetime(2026, 11, 15, tzinfo=UTC)))


if __name__ == "__main__":
    unittest.main()
