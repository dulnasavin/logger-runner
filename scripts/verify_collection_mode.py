"""Protected switch: exactly one five-minute collection generation is enabled."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

DEFAULT = Path(__file__).resolve().parent.parent / "config" / "five_minute_collection.json"


def verify(path: Path, required: str) -> str:
    if required not in {"legacy", "v2"}:
        raise ValueError("Unknown requested collection mode")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(payload, dict)
            or type(payload.get("schema_version")) is not int or payload["schema_version"] != 1
            or payload.get("mode") not in {"legacy", "v2"}
            or (payload["mode"] == "legacy" and set(payload) != {"schema_version", "mode"})
            or (payload["mode"] == "v2" and set(payload) != {"schema_version", "mode", "first_slot_utc"})):
        raise ValueError("Invalid protected collection mode")
    if payload["mode"] == "v2":
        from five_minute_watchdog import parse_slot
        parse_slot(payload["first_slot_utc"])
    if payload["mode"] != required:
        raise ValueError(f"Collection mode is {payload['mode']}; {required} is disabled")
    return required


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--require", required=True, choices=("legacy", "v2"))
    parser.add_argument("--path", type=Path, default=DEFAULT)
    args = parser.parse_args()
    print(verify(args.path, args.require))
