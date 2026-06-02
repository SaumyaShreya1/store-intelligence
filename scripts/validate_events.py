"""
scripts/validate_events.py

Validates that a .jsonl events file produced by pipeline/detect.py
conforms to the expected schema.  Used in CI smoke-test step.

Usage
-----
python scripts/validate_events.py --file /tmp/events_test.jsonl
"""

import argparse
import json
import sys

REQUIRED_FIELDS = {"event_id", "event_type", "track_id", "store_id", "camera_id", "timestamp"}
VALID_EVENT_TYPES = {"entry", "exit", "appear", "disappear", "zone_enter", "zone_exit", "dwell"}


def validate(path: str):
    errors = []
    with open(path) as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError as e:
                errors.append(f"Line {lineno}: invalid JSON — {e}")
                continue

            missing = REQUIRED_FIELDS - ev.keys()
            if missing:
                errors.append(f"Line {lineno}: missing fields {missing}")

            if ev.get("event_type") not in VALID_EVENT_TYPES:
                errors.append(
                    f"Line {lineno}: unknown event_type '{ev.get('event_type')}'"
                )

    if errors:
        for e in errors:
            print(f"[validate] ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"[validate] OK — file passed schema validation: {path}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--file", required=True)
    args = p.parse_args()
    validate(args.file)
