import json
import tempfile
import unittest
from pathlib import Path

from five_minute_release import digest, expected, stage, verify


class ReleaseTests(unittest.TestCase):
    def archive(self, root):
        archive = root / "archive"
        assets = {}
        for n in range(102):
            symbol = f"C{n}"
            path = archive / symbol / "2026" / "11.csv"
            path.parent.mkdir(parents=True)
            path.write_text("timestamp_nz,symbol\n")
            assets[f"{symbol}/2026/11.csv"] = {"rows": 0, "sha256": digest(path)}
        (archive / "manifest.json").write_text(json.dumps({"version": 1, "generation": 1,
            "month_nz": "2026-11", "status": "PARTIAL", "assets": assets}))
        return archive

    def test_stage_and_verify_detect_corrupt_and_missing_asset(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = self.archive(root)
            staged = root / "staged"
            stage(archive, staged)
            self.assertEqual(len(list(staged.iterdir())), 103)
            verify(archive, staged)
            (staged / "C1-2026-11.csv").write_text("tampered")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                verify(archive, staged)
            (staged / "C1-2026-11.csv").unlink()
            with self.assertRaisesRegex(ValueError, "set differs"):
                verify(archive, staged)

    def test_manifest_path_and_source_hash_are_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = self.archive(root)
            data = json.loads((archive / "manifest.json").read_text())
            data["assets"]["../2026/11.csv"] = data["assets"].pop("C1/2026/11.csv")
            (archive / "manifest.json").write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "Unsafe"):
                expected(archive)
            data["assets"]["C1/2026/11.csv"] = data["assets"].pop("../2026/11.csv")
            (archive / "manifest.json").write_text(json.dumps(data))
            (archive / "C1/2026/11.csv").write_text("changed")
            with self.assertRaisesRegex(ValueError, "Source asset hash mismatch"):
                stage(archive, root / "staged")
            self.assertFalse((root / "staged").exists())


if __name__ == "__main__":
    unittest.main()
