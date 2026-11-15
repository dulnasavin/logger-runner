"""Plan a bounded, durable audit of every expected five-minute UTC slot.

The watermark advances only when its corresponding gap record is published in
the same fast-forward commit. An outage can make this lag; subsequent runs
catch up one day at a time without skipping slots.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

UTC = timezone.utc
SLOT = timedelta(minutes=5)
GRACE = timedelta(minutes=15)
MAX_SLOTS = 288


def parse_slot(value):
    if not isinstance(value, str) or len(value) != 20 or not value.endswith("Z"):
        raise ValueError("Invalid UTC slot")
    try:
        stamp = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as error:
        raise ValueError("Invalid UTC slot") from error
    if stamp.minute % 5:
        raise ValueError("Slot is not five-minute aligned")
    return stamp


def stamp(value):
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def plan(config, state, now):
    if not isinstance(config, dict) or config.get("schema_version") != 1:
        raise ValueError("Invalid protected mode")
    if config.get("mode") == "legacy":
        if set(config) != {"schema_version", "mode"}:
            raise ValueError("Invalid legacy mode")
        return None
    if config.get("mode") != "v2" or set(config) != {"schema_version", "mode", "first_slot_utc"}:
        raise ValueError("v2 requires a protected first slot")
    first = parse_slot(config["first_slot_utc"])
    if now.tzinfo is None:
        raise ValueError("Naive current time")
    end = (now.astimezone(UTC) - GRACE).replace(second=0, microsecond=0)
    end = end.replace(minute=end.minute // 5 * 5)
    if first > end + GRACE:
        raise ValueError("Protected first slot is in the future")
    previous = first - SLOT
    if state is not None:
        if (not isinstance(state, dict) or set(state) != {"version", "first_slot_utc", "last_audited_slot_utc"}
                or state["version"] != 1 or state["first_slot_utc"] != config["first_slot_utc"]):
            raise ValueError("Audit watermark conflicts with protected first slot")
        previous = parse_slot(state["last_audited_slot_utc"])
        if previous < first - SLOT or previous > end:
            raise ValueError("Audit watermark outside expected range")
    begin = previous + SLOT
    if begin > end:
        return None
    bounded = min(end, begin + SLOT * (MAX_SLOTS - 1))
    return {"start": stamp(begin), "end": stamp(bounded),
            "remaining_slots": int((end - bounded) // SLOT),
            "next_state": {"version": 1, "first_slot_utc": config["first_slot_utc"],
                           "last_audited_slot_utc": stamp(bounded)}}


def record(batch, gaps, roster):
    if not isinstance(batch, dict) or not isinstance(gaps, dict):
        raise ValueError("Invalid audit report")
    begin, end = parse_slot(batch["start"]), parse_slot(batch["end"])
    slots = {stamp(begin + SLOT * i) for i in range(int((end - begin) // SLOT) + 1)}
    expected = set(roster)
    if not expected or any(key not in slots or not isinstance(value, list)
            or not value or len(value) != len(set(value)) or not set(value) <= expected
            for key, value in gaps.items()):
        raise ValueError("Audit returned invalid slot or market")
    return {"version": 1, "start": batch["start"], "end": batch["end"],
            "expected_slots": len(slots), "expected_markets_per_slot": len(expected),
            "missing_symbols": sum(map(len, gaps.values())),
            "gaps": {key: sorted(value) for key, value in sorted(gaps.items())}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("plan", "record"))
    parser.add_argument("--mode", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--gaps", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    mode = json.loads(args.mode.read_text())
    state = json.loads(args.state.read_text()) if args.state.exists() else None
    if args.command == "plan":
        result = plan(mode, state, datetime.now(UTC))
    else:
        if not args.plan or not args.gaps or not args.output:
            parser.error("record requires --plan, --gaps, and --output")
        from market_roster import SYMBOLS
        batch = json.loads(args.plan.read_text())
        result = record(batch, json.loads(args.gaps.read_text()), SYMBOLS)
        args.output.write_text(json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n")
    print(json.dumps(result, sort_keys=True))
