import csv
import json
import tempfile
import unittest
from pathlib import Path

from scripts.manage_csv_file_lifecycle import (
    CsvLifecycleError,
    DELETE_CONFIRMATION,
    EXPECTED_HEADER,
    delete_empty_csv,
    guard_recovery,
)


class CsvFileLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.csv_path = self.root / "price_log.csv"
        self.state_path = self.root / "csv_state.json"
        self._write_state(last_action="intentional_reset")
        self._write_csv([])

    def tearDown(self):
        self.temporary.cleanup()

    def _write_state(self, **updates):
        state = {
            "format_version": 1,
            "schema_version": 1,
            "generation": 2,
            "last_action": "intentional_reset",
            "reason": "test reset",
        }
        state.update(updates)
        self.state_path.write_text(json.dumps(state), encoding="utf-8")

    def _write_csv(self, rows):
        with self.csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(EXPECTED_HEADER)
            writer.writerows(rows)

    def test_deletes_header_only_csv_after_reset(self):
        report = delete_empty_csv(
            self.csv_path,
            self.state_path,
            confirmation=DELETE_CONFIRMATION,
            reason="Retire the CSV file",
        )
        self.assertFalse(self.csv_path.exists())
        self.assertEqual(report["status"], "intentionally-deleted")
        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertEqual(state["last_action"], "intentional_file_delete")
        self.assertEqual(state["file_status"], "intentionally_deleted")

    def test_rejects_csv_with_data_rows(self):
        self._write_csv([["2026-09-03 18:00:00", "ETH", "1", "2", "OK", "2"]])
        with self.assertRaisesRegex(CsvLifecycleError, "intentional-reset first"):
            delete_empty_csv(
                self.csv_path,
                self.state_path,
                confirmation=DELETE_CONFIRMATION,
                reason="Retire it",
            )
        self.assertTrue(self.csv_path.exists())

    def test_rejects_extra_blank_row(self):
        with self.csv_path.open("a", encoding="utf-8") as handle:
            handle.write("\n")
        with self.assertRaisesRegex(CsvLifecycleError, "rows beyond its header"):
            delete_empty_csv(
                self.csv_path,
                self.state_path,
                confirmation=DELETE_CONFIRMATION,
                reason="Retire it",
            )

    def test_rejects_symbolic_link(self):
        target = self.root / "real.csv"
        self.csv_path.replace(target)
        self.csv_path.symlink_to(target)
        with self.assertRaisesRegex(CsvLifecycleError, "symbolic links"):
            delete_empty_csv(
                self.csv_path,
                self.state_path,
                confirmation=DELETE_CONFIRMATION,
                reason="Retire it",
            )

    def test_rejects_without_immediately_preceding_reset(self):
        self._write_state(last_action="delete_selected_batches")
        with self.assertRaisesRegex(CsvLifecycleError, "immediately preceded"):
            delete_empty_csv(
                self.csv_path,
                self.state_path,
                confirmation=DELETE_CONFIRMATION,
                reason="Retire it",
            )

    def test_rejects_wrong_confirmation(self):
        with self.assertRaisesRegex(CsvLifecycleError, DELETE_CONFIRMATION):
            delete_empty_csv(
                self.csv_path,
                self.state_path,
                confirmation="DELETE",
                reason="Retire it",
            )

    def test_guard_blocks_deliberately_missing_file(self):
        self.csv_path.unlink()
        self._write_state(
            last_action="intentional_file_delete",
            file_status="intentionally_deleted",
        )
        with self.assertRaisesRegex(CsvLifecycleError, "must not be restored"):
            guard_recovery(self.csv_path, self.state_path)

    def test_guard_allows_accidentally_missing_file(self):
        self.csv_path.unlink()
        report = guard_recovery(self.csv_path, self.state_path)
        self.assertEqual(report["status"], "recovery-allowed")

    def test_guard_fails_on_inconsistent_file_and_retired_state(self):
        self._write_state(
            last_action="intentional_file_delete",
            file_status="intentionally_deleted",
        )
        with self.assertRaisesRegex(CsvLifecycleError, "file exists"):
            guard_recovery(self.csv_path, self.state_path)


if __name__ == "__main__":
    unittest.main()
