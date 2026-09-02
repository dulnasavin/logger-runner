import copy
import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_release_manifest", ROOT / "scripts" / "validate_release_manifest.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def valid_manifest():
    return {
        "schema_version": 1,
        "environment": "production",
        "private_repository": MODULE.EXPECTED_REPOSITORY,
        "private_commit_sha": "a" * 40,
        "private_data_branch": "runtime-data",
        "capabilities": {
            "logger": "disabled",
            "runtime_maintenance": "disabled",
            "neon": "disabled",
        },
    }


class ReleaseManifestTests(unittest.TestCase):
    def test_review_accepts_complete_manifest_states(self):
        for state in ("disabled", "enabled"):
            with self.subTest(state=state):
                value = valid_manifest()
                value["capabilities"]["logger"] = state
                result = MODULE.validate_manifest(value, capability=None, execute=False)
                self.assertEqual(result["private_commit_sha"], "a" * 40)

    def test_execution_fails_closed_while_capability_disabled(self):
        with self.assertRaisesRegex(MODULE.ReleaseManifestError, "disabled"):
            MODULE.validate_manifest(valid_manifest(), capability="logger", execute=True)

    def test_execution_accepts_only_explicitly_enabled_capability(self):
        value = valid_manifest()
        value["capabilities"]["logger"] = "enabled"
        MODULE.validate_manifest(value, capability="logger", execute=True)
        with self.assertRaisesRegex(MODULE.ReleaseManifestError, "disabled"):
            MODULE.validate_manifest(value, capability="neon", execute=True)

    def test_unknown_key_fails_closed(self):
        value = valid_manifest()
        value["unreviewed_override"] = True
        with self.assertRaisesRegex(MODULE.ReleaseManifestError, "unknown"):
            MODULE.validate_manifest(value, capability=None, execute=False)

    def test_repository_data_branch_and_sha_are_immutable_schema_fields(self):
        mutations = (
            ("private_repository", "attacker/repository"),
            ("private_data_branch", "main"),
            ("private_commit_sha", "0" * 40),
            ("private_commit_sha", "ABC"),
        )
        for field, replacement in mutations:
            with self.subTest(field=field, replacement=replacement):
                value = copy.deepcopy(valid_manifest())
                value[field] = replacement
                with self.assertRaises(MODULE.ReleaseManifestError):
                    MODULE.validate_manifest(value, capability=None, execute=False)

    def test_capability_schema_must_be_complete(self):
        value = valid_manifest()
        del value["capabilities"]["neon"]
        with self.assertRaisesRegex(MODULE.ReleaseManifestError, "complete schema"):
            MODULE.validate_manifest(value, capability=None, execute=False)


if __name__ == "__main__":
    unittest.main()
