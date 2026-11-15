import json
import tempfile
import unittest
from pathlib import Path
from verify_collection_mode import verify


class ModeTests(unittest.TestCase):
    def test_only_selected_generation_can_collect(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "mode.json"
            file.write_text(json.dumps({"schema_version": 1, "mode": "legacy"}))
            self.assertEqual(verify(file, "legacy"), "legacy")
            with self.assertRaisesRegex(ValueError, "disabled"):
                verify(file, "v2")
            file.write_text(json.dumps({"schema_version": 1, "mode": "v2"}))
            self.assertEqual(verify(file, "v2"), "v2")
            with self.assertRaisesRegex(ValueError, "disabled"):
                verify(file, "legacy")

    def test_unknown_fields_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "mode.json"
            file.write_text(json.dumps({"schema_version": 1, "mode": "v2", "extra": True}))
            with self.assertRaisesRegex(ValueError, "Invalid"):
                verify(file, "v2")


if __name__ == "__main__":
    unittest.main()
