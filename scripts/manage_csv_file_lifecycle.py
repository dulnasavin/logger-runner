#!/usr/bin/env python3
"""Fail-closed lifecycle controls for intentionally deleting price_log.csv."""

from __future__ import annotations

import argparse
import csv
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


EXPECTED_HEADER = [
    "timestamp_nz",
    "symbol",
    "price_usd",
    "price_nzd",
    "status",
    "usd_nzd_rate",
]
DELETE_CONFIRMATION = "DELETE_EMPTY_CSV_FILE"
DELETE_ACTION = "intentional_file_delete"
MAX_REASON_LENGTH = 200


class CsvLifecycleError(RuntimeError):
    """Raised when a lifecycle operation is unsafe or inconsistent."""


def _read_state(path: Path) -> dict:
    if not path.is_file():
        raise CsvLifecycleError(f"CSV state file is missing: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CsvLifecycleError("CSV state file is unreadable or invalid JSON") from error
    if not isinstance(payload, dict):
        raise CsvLifecycleError("CSV state root must be an object")
    try:
        format_version = int(payload.get("format_version", 0))
        schema_version = int(payload.get("schema_version", 0))
        generation = int(payload.get("generation", 0))
    except (TypeError, ValueError) as error:
        raise CsvLifecycleError("CSV state version or generation is invalid") from error
    if format_version != 1 or schema_version != 1 or generation < 1:
        raise CsvLifecycleError("CSV state version or generation is unsupported")
    return payload


def _atomic_write_json(path: Path, payload: dict) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def delete_empty_csv(
    csv_path: Path,
    state_path: Path,
    *,
    confirmation: str,
    reason: str,
) -> dict:
    if confirmation != DELETE_CONFIRMATION:
        raise CsvLifecycleError(
            f"Empty-file deletion requires exact confirmation {DELETE_CONFIRMATION}"
        )
    reason = reason.strip()
    if not reason:
        raise CsvLifecycleError("Empty-file deletion requires a non-empty reason")
    if len(reason) > MAX_REASON_LENGTH:
        raise CsvLifecycleError(
            f"Empty-file deletion reason must be {MAX_REASON_LENGTH} characters or fewer"
        )
    if csv_path.is_symlink() or state_path.is_symlink():
        raise CsvLifecycleError("CSV lifecycle files must not be symbolic links")
    if not csv_path.is_file():
        raise CsvLifecycleError("CSV file is already missing; no deletion was performed")

    try:
        with csv_path.open("r", newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.reader(handle))
    except (OSError, UnicodeError, csv.Error) as error:
        raise CsvLifecycleError("CSV file is unreadable or malformed") from error
    if not rows or rows[0] != EXPECTED_HEADER:
        raise CsvLifecycleError("CSV must contain the exact canonical header")
    if len(rows) != 1:
        raise CsvLifecycleError(
            "CSV contains rows beyond its header; run intentional-reset first, then retry deletion"
        )

    state = _read_state(state_path)
    if state.get("last_action") != "intentional_reset":
        raise CsvLifecycleError(
            "CSV state does not prove an intentional reset immediately preceded deletion; "
            "run intentional-reset first"
        )

    now = datetime.now(timezone.utc).isoformat()
    state.update(
        {
            "last_action": DELETE_ACTION,
            "file_status": "intentionally_deleted",
            "file_deleted_at_utc": now,
            "file_delete_reason": reason,
        }
    )
    _atomic_write_json(state_path, state)
    csv_path.unlink()
    return {
        "status": "intentionally-deleted",
        "generation": int(state["generation"]),
        "rows": 0,
    }


def guard_recovery(csv_path: Path, state_path: Path) -> dict:
    if csv_path.is_symlink() or state_path.is_symlink():
        raise CsvLifecycleError("CSV lifecycle files must not be symbolic links")
    state = _read_state(state_path)
    intentionally_deleted = (
        state.get("last_action") == DELETE_ACTION
        or state.get("file_status") == "intentionally_deleted"
    )
    if intentionally_deleted:
        if csv_path.exists():
            raise CsvLifecycleError(
                "CSV state says the file is intentionally deleted, but the file exists; "
                "run intentional-reset to establish a consistent new generation"
            )
        raise CsvLifecycleError(
            "price_log.csv was intentionally deleted and must not be restored; "
            "run CSV Maintenance intentional-reset to create a new empty generation"
        )
    return {"status": "recovery-allowed", "generation": int(state["generation"])}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True, choices=("delete-empty", "guard-recovery"))
    parser.add_argument("--path", required=True, type=Path)
    parser.add_argument("--state-path", required=True, type=Path)
    parser.add_argument("--confirmation", default="")
    parser.add_argument("--reason", default="")
    args = parser.parse_args()
    try:
        if args.mode == "delete-empty":
            report = delete_empty_csv(
                args.path,
                args.state_path,
                confirmation=args.confirmation,
                reason=args.reason,
            )
        else:
            report = guard_recovery(args.path, args.state_path)
    except CsvLifecycleError as error:
        parser.error(str(error))
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
