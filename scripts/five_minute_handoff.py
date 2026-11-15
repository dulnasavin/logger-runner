"""Pure routing rules for one claimed five-minute collection slot."""
from __future__ import annotations

import argparse
import base64
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

UTC = timezone.utc
LANES = ("main", "main2", "main3")
ACTIVE = frozenset(("queued", "waiting", "pending", "requested", "in_progress"))
TITLE = re.compile(r"Crypto Logger \| (main|main2|main3) \| (\d{4}-\d\d-\d\dT\d\d:\d\d:00Z)\Z")


class HandoffError(ValueError):
    pass


def parse_slot(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:00Z", value):
        raise HandoffError("Invalid UTC slot")
    try:
        slot = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as error:
        raise HandoffError("Invalid calendar date") from error
    if slot.minute % 5:
        raise HandoffError("Slot is not aligned to five minutes")
    return slot


def seconds_until_handoff(slot_utc, now, lead_seconds=10):
    slot = parse_slot(slot_utc)
    now = now.astimezone(UTC)
    if not 0 <= lead_seconds <= 60:
        raise HandoffError("Unsupported lead time")
    if now < slot - timedelta(minutes=3) or now > slot + timedelta(minutes=4, seconds=30):
        raise HandoffError("Dispatcher is outside this slot's safe window")
    return max(0, (slot - timedelta(seconds=lead_seconds) - now).total_seconds())


def choose_lane(runs, slot_utc):
    parse_slot(slot_utc)
    if not isinstance(runs, dict) or not isinstance(runs.get("workflow_runs"), list):
        raise HandoffError("Actions run inventory unavailable")
    busy = set()
    for run in runs["workflow_runs"]:
        if not isinstance(run, dict) or not isinstance(run.get("status"), str):
            raise HandoffError("Malformed Actions run")
        matched = TITLE.fullmatch(run.get("display_title") or "")
        if not matched:
            if run["status"] in ACTIVE:
                # Unknown active run identity is not proof that any lane is free.
                raise HandoffError("Unidentified active collector run")
            continue
        lane, run_slot = matched.groups()
        if run_slot == slot_utc:
            raise HandoffError("Slot already dispatched; inspect its existing run")
        if run["status"] in ACTIVE:
            busy.add(lane)
    for lane in LANES:
        if lane not in busy:
            return lane
    raise HandoffError("All three collector lanes are occupied")


def claim_path(slot_utc):
    slot = parse_slot(slot_utc)
    return f"five_minute/claims/{slot:%Y/%m/%d/%H%M}.json"


def make_claim(slot_utc, lane, dispatcher_run_id, now):
    if lane not in LANES or not re.fullmatch(r"[0-9]{1,20}", str(dispatcher_run_id)):
        raise HandoffError("Invalid lane or dispatcher identity")
    seconds_until_handoff(slot_utc, now)
    return {
        "version": 1, "slot_utc": slot_utc, "lane": lane,
        "dispatcher_run_id": str(dispatcher_run_id),
        "assigned_at_utc": now.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def verify_claim(api_response, slot_utc, lane, dispatcher_run_id):
    if not isinstance(api_response, dict) or api_response.get("type") != "file":
        raise HandoffError("Missing private dispatch claim")
    if api_response.get("path") != claim_path(slot_utc) or api_response.get("encoding") != "base64":
        raise HandoffError("Wrong claim path or encoding")
    try:
        encoded = api_response["content"]
        if not isinstance(encoded, str) or len(encoded) > 4096:
            raise ValueError("Oversized claim")
        content = base64.b64decode("".join(encoded.split()), validate=True)
        claim = json.loads(content)
    except (KeyError, ValueError, TypeError) as error:
        raise HandoffError("Invalid claim contents") from error
    if (set(claim) != {"version", "slot_utc", "lane", "dispatcher_run_id", "assigned_at_utc"}
            or claim["version"] != 1 or claim["slot_utc"] != slot_utc
            or claim["lane"] != lane or claim["dispatcher_run_id"] != str(dispatcher_run_id)):
        raise HandoffError("Collector does not own this slot")
    try:
        datetime.strptime(claim["assigned_at_utc"], "%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError) as error:
        raise HandoffError("Invalid claim time") from error
    return claim


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("wait", "choose", "claim", "verify", "path"))
    parser.add_argument("--slot", required=True)
    parser.add_argument("--lane")
    parser.add_argument("--run-id")
    parser.add_argument("--input")
    parser.add_argument("--output")
    parser.add_argument("--lead-seconds", type=int, default=10)
    args = parser.parse_args()
    now = datetime.now(UTC)
    if args.command == "wait":
        print(seconds_until_handoff(args.slot, now, args.lead_seconds))
    elif args.command == "choose":
        print(choose_lane(json.loads(Path(args.input).read_text()), args.slot))
    elif args.command == "path":
        print(claim_path(args.slot))
    elif args.command == "claim":
        claim = make_claim(args.slot, args.lane, args.run_id, now)
        Path(args.output).write_text(json.dumps(claim, sort_keys=True, separators=(",", ":")) + "\n")
    else:
        verify_claim(json.loads(Path(args.input).read_text()), args.slot, args.lane, args.run_id)


if __name__ == "__main__":
    main()
