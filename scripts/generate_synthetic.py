"""Generate synthetic JSONL events for testing without real video clips."""
import json, random, time
from datetime import datetime, timedelta
from pathlib import Path

STORE_ID = "STORE_PURPLLE_001"
CAMERAS = ["CAM_FLOOR_01", "CAM_FLOOR_02", "CAM_ENTRY_01", "CAM_BILLING_01"]
ZONES = ["SKINCARE", "MAKEUP_WALL", "ENTRY", "BILLING_COUNTER"]
EVENTS = ["entry", "exit", "dwell", "queue_join"]

Path("data").mkdir(exist_ok=True)
output = "data/events_all.jsonl"
start = datetime.now() - timedelta(hours=1)
events = []
for i in range(500):
    t = start + timedelta(seconds=random.randint(0, 3600))
    events.append({
        "store_id": STORE_ID,
        "camera_id": random.choice(CAMERAS),
        "zone": random.choice(ZONES),
        "event_type": random.choice(EVENTS),
        "visitor_id": f"V{random.randint(1000,2000):04d}",
        "timestamp": t.isoformat(),
        "dwell_ms": random.randint(500, 5000)
    })
events.sort(key=lambda x: x["timestamp"])
with open(output, "w") as f:
    for e in events:
        f.write(json.dumps(e) + "\n")
print(f"Generated {len(events)} events -> {output}")
