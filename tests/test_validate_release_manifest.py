import copy
import importlib.util
import json
import os
import shlex
import subprocess
import sys
import tempfile
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
        "schema_version": 2,
        "environment": "production",
        "private_repository": MODULE.EXPECTED_REPOSITORY,
        "private_commit_sha": "a" * 40,
        "private_data_branch": "runtime-data",
        "capabilities": {
            "logger": "disabled",
            "runtime_maintenance": "disabled",
            "neon": "disabled",
            "neon_schema": "disabled",
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
        for capability in MODULE.CAPABILITIES:
            with self.subTest(capability=capability):
                with self.assertRaisesRegex(MODULE.ReleaseManifestError, "disabled"):
                    MODULE.validate_manifest(valid_manifest(), capability=capability, execute=True)

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

    def test_schema_and_data_permissions_are_independent(self):
        for enabled in MODULE.CAPABILITIES:
            value = valid_manifest()
            value["capabilities"][enabled] = "enabled"
            for requested in MODULE.CAPABILITIES:
                with self.subTest(enabled=enabled, requested=requested):
                    if requested == enabled:
                        MODULE.validate_manifest(value, capability=requested, execute=True)
                    else:
                        with self.assertRaisesRegex(MODULE.ReleaseManifestError, "disabled"):
                            MODULE.validate_manifest(value, capability=requested, execute=True)

    def test_old_missing_and_malformed_permissions_fail_closed(self):
        for version in (1, True, 2.0, "2", None):
            with self.subTest(version=version):
                value = valid_manifest()
                value["schema_version"] = version
                with self.assertRaisesRegex(MODULE.ReleaseManifestError, "unsupported"):
                    MODULE.validate_manifest(value, capability=None, execute=False)
        value = valid_manifest()
        del value["capabilities"]["neon_schema"]
        with self.assertRaisesRegex(MODULE.ReleaseManifestError, "complete schema"):
            MODULE.validate_manifest(value, capability=None, execute=False)
        for state in (True, [], {}, None):
            with self.subTest(state=state):
                value = valid_manifest()
                value["capabilities"]["neon_schema"] = state
                with self.assertRaisesRegex(MODULE.ReleaseManifestError, "invalid states"):
                    MODULE.validate_manifest(value, capability="neon_schema", execute=True)

    def test_workflow_commands_cannot_cross_enable_schema_and_data(self):
        # Execute the actual workflow gate commands against temporary policies.
        workflows = {
            "neon_schema_migrate.yml": "neon_schema",
            "neon_reconciliation.yml": "neon",
        }
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / "release.json"
            output = Path(directory) / "outputs"
            env = dict(os.environ, GITHUB_OUTPUT=str(output))
            for filename, capability in workflows.items():
                workflow = (ROOT / ".github" / "workflows" / filename).read_text()
                command = "python scripts/validate_release_manifest.py" + workflow.split(
                    "python scripts/validate_release_manifest.py", 1
                )[1].split("\n\n", 1)[0]
                arguments = shlex.split(command.replace('"$GITHUB_OUTPUT"', str(output)))
                arguments[0] = sys.executable
                arguments += ["--manifest", str(manifest)]
                for enabled in ("neon_schema", "neon"):
                    value = valid_manifest()
                    value["capabilities"][enabled] = "enabled"
                    manifest.write_text(json.dumps(value))
                    output.unlink(missing_ok=True)
                    result = subprocess.run(arguments, cwd=ROOT, env=env,
                                            text=True, capture_output=True)
                    with self.subTest(workflow=filename, enabled=enabled):
                        if enabled == capability:
                            self.assertEqual(result.returncode, 0, result.stderr)
                            entries = dict(line.split("=", 1) for line in output.read_text().splitlines())
                            self.assertEqual(entries[f"{capability}_state"], "enabled")
                            other = "neon" if capability == "neon_schema" else "neon_schema"
                            self.assertEqual(entries[f"{other}_state"], "disabled")
                        else:
                            self.assertEqual(result.returncode, 2)
                            self.assertIn("disabled by protected release policy", result.stderr)
                            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
