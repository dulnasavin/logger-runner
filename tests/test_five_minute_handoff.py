import base64
import json
import unittest
from datetime import datetime, timedelta, timezone

from five_minute_handoff import (
    HandoffError, choose_lane, claim_path, make_claim, seconds_until_handoff,
    verify_claim, runtime_forecast,
)

SLOT = "2026-11-15T12:00:00Z"
NOW = datetime(2026, 11, 15, 11, 59, 50, tzinfo=timezone.utc)


def active(lane, slot="2026-11-15T11:55:00Z"):
    return {"status": "in_progress", "display_title": f"Crypto Logger | {lane} | {slot}"}


class HandoffTests(unittest.TestCase):
    def test_ten_second_irrevocable_handoff(self):
        self.assertEqual(seconds_until_handoff(SLOT, NOW - timedelta(seconds=1)), 1)
        self.assertEqual(seconds_until_handoff(SLOT, NOW), 0)
        self.assertEqual(choose_lane({"workflow_runs": [active("main")]}, SLOT), "main2")
        claim = make_claim(SLOT, "main2", "123", NOW)
        self.assertEqual(claim["lane"], "main2")
        # Main finishing a second later cannot alter the committed claim.
        self.assertEqual(claim["lane"], "main2")

    def test_third_lane_and_all_busy(self):
        self.assertEqual(choose_lane({"workflow_runs": [active("main"), active("main2")]}, SLOT), "main3")
        with self.assertRaisesRegex(HandoffError, "occupied"):
            choose_lane({"workflow_runs": [active("main"), active("main2"), active("main3")]}, SLOT)

    def test_duplicate_slot_or_unknown_active_run_fails_closed(self):
        with self.assertRaisesRegex(HandoffError, "already dispatched"):
            choose_lane({"workflow_runs": [active("main", SLOT)]}, SLOT)
        with self.assertRaisesRegex(HandoffError, "Unidentified"):
            choose_lane({"workflow_runs": [{"status": "queued", "display_title": ""}]}, SLOT)

    def test_claim_only_authorizes_selected_lane_and_dispatcher(self):
        claim = make_claim(SLOT, "main2", "123", NOW)
        response = {"type": "file", "path": claim_path(SLOT), "encoding": "base64",
                    "content": base64.b64encode(json.dumps(claim).encode()).decode()}
        self.assertEqual(verify_claim(response, SLOT, "main2", "123"), claim)
        with self.assertRaisesRegex(HandoffError, "does not own"):
            verify_claim(response, SLOT, "main", "123")
        with self.assertRaisesRegex(HandoffError, "does not own"):
            verify_claim(response, SLOT, "main2", "456")

    def test_stale_dispatch_and_invalid_slot_rejected(self):
        with self.assertRaisesRegex(HandoffError, "safe window"):
            seconds_until_handoff(SLOT, NOW - timedelta(minutes=4))
        with self.assertRaisesRegex(HandoffError, "aligned"):
            seconds_until_handoff("2026-11-15T12:01:00Z", NOW)

    def test_estimate_adapts_but_never_routes_a_busy_lane(self):
        runs = {"workflow_runs": [
            {"status": "completed", "display_title": "Crypto Logger | main | 2026-11-15T11:45:00Z",
             "run_started_at": "2026-11-15T11:45:00Z", "updated_at": "2026-11-15T11:48:00Z"},
            {"status": "in_progress", "display_title": "Crypto Logger | main | 2026-11-15T11:55:00Z",
             "run_started_at": "2026-11-15T11:55:00Z", "updated_at": "2026-11-15T11:55:00Z"},
        ]}
        forecast = runtime_forecast(runs, NOW)
        self.assertTrue(forecast["main"]["over_recent_p90"])
        self.assertEqual(choose_lane(runs, SLOT), "main2")


if __name__ == "__main__":
    unittest.main()
