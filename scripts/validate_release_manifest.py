"""Validate the public, review-controlled production release manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


EXPECTED_REPOSITORY = "dulnasavin/Repository-name-crypto-tracker-Private-Yes"
EXPECTED_DATA_BRANCH = "runtime-data"
CAPABILITIES = frozenset({"logger", "runtime_maintenance", "neon"})
STATES = frozenset({"disabled", "enabled"})
TOP_LEVEL_KEYS = frozenset(
    {
        "schema_version",
        "environment",
        "private_repository",
        "private_commit_sha",
        "private_data_branch",
        "capabilities",
    }
)


class ReleaseManifestError(ValueError):
    """Raised when release authority is malformed or unsafe."""


def load_manifest(path: Path) -> tuple[dict, bytes]:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise ReleaseManifestError("release manifest is unavailable") from error
    if not raw or len(raw) > 16_384:
        raise ReleaseManifestError("release manifest has an invalid size")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ReleaseManifestError("release manifest is not valid UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise ReleaseManifestError("release manifest must be one JSON object")
    return value, raw


def validate_manifest(value: dict, *, capability: str | None, execute: bool) -> dict:
    keys = frozenset(value)
    if keys != TOP_LEVEL_KEYS:
        missing = sorted(TOP_LEVEL_KEYS - keys)
        unknown = sorted(keys - TOP_LEVEL_KEYS)
        raise ReleaseManifestError(
            f"release manifest keys do not match schema; missing={missing}; unknown={unknown}"
        )
    if value["schema_version"] != 1:
        raise ReleaseManifestError("unsupported release manifest schema")
    if value["environment"] != "production":
        raise ReleaseManifestError("release manifest environment must be production")
    if value["private_repository"] != EXPECTED_REPOSITORY:
        raise ReleaseManifestError("private repository does not match the approved target")
    if value["private_data_branch"] != EXPECTED_DATA_BRANCH:
        raise ReleaseManifestError("private data branch does not match runtime-data")

    commit = value["private_commit_sha"]
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ReleaseManifestError("private commit must be one lowercase full SHA")
    if commit == "0" * 40:
        raise ReleaseManifestError("private commit cannot be the null SHA")

    capabilities = value["capabilities"]
    if not isinstance(capabilities, dict) or frozenset(capabilities) != CAPABILITIES:
        raise ReleaseManifestError("release capabilities do not match the complete schema")
    invalid_states = sorted(
        name for name, state in capabilities.items() if state not in STATES
    )
    if invalid_states:
        raise ReleaseManifestError(
            "release capabilities have invalid states: " + ", ".join(invalid_states)
        )

    if execute:
        if capability not in CAPABILITIES:
            raise ReleaseManifestError("execution requires one known capability")
        if capabilities[capability] != "enabled":
            raise ReleaseManifestError(
                f"production capability {capability!r} is disabled by protected release policy"
            )
    elif capability is not None:
        raise ReleaseManifestError("review mode does not accept an execution capability")
    return value


def write_github_output(path: Path, manifest: dict, digest: str) -> None:
    outputs = {
        "private_repository": manifest["private_repository"],
        "private_code_sha": manifest["private_commit_sha"],
        "private_data_branch": manifest["private_data_branch"],
        "manifest_sha256": digest,
        "logger_state": manifest["capabilities"]["logger"],
        "runtime_maintenance_state": manifest["capabilities"]["runtime_maintenance"],
        "neon_state": manifest["capabilities"]["neon"],
    }
    with path.open("a", encoding="utf-8", newline="\n") as output:
        for name, value in outputs.items():
            output.write(f"{name}={value}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest", type=Path, default=Path("config/production-release.json")
    )
    parser.add_argument("--mode", choices=("review", "execute"), required=True)
    parser.add_argument("--capability", choices=sorted(CAPABILITIES))
    parser.add_argument("--github-output", type=Path)
    arguments = parser.parse_args()

    try:
        value, raw = load_manifest(arguments.manifest)
        manifest = validate_manifest(
            value,
            capability=arguments.capability,
            execute=arguments.mode == "execute",
        )
        digest = hashlib.sha256(raw).hexdigest()
        if arguments.github_output:
            write_github_output(arguments.github_output, manifest, digest)
    except ReleaseManifestError as error:
        parser.error(str(error))

    states = ", ".join(
        f"{name}={manifest['capabilities'][name]}" for name in sorted(CAPABILITIES)
    )
    print(f"Release manifest valid: sha256:{digest[:16]}; {states}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
