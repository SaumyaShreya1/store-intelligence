"""Generate synthetic events matching the actual Purplle sample event schema."""
import json, random, uuid
from datetime import datetime, timedelta
from pathlib import Path

Path("data").mkdir(exist_ok=True)
output = "data/events_all.jsonl"

STORE_CODE = "store_1076"
STORE_ID = "ST1076"
ZONES = [
    {"zone_id": "PURPLLE_MUM_1076_Z01", "zone_name": "Left Shelf", "zone_type": "SHELF", "is_revenue_zone": "Yes"},
    {"zone_id": "PURPLLE_MUM_1076_Z02", "zone_name": "Center Display", "zone_type": "DISPLAY", "is_revenue_zone": "Yes"},
    {"zone_id": "PURPLLE_MUM_1076_Z03", "zone_name": "Lipstick Aisle", "zone_type": "SHELF", "is_revenue_zone": "Yes"},
    {"zone_id": "PURPLLE_MUM_1076_Z_BILLING_01", "zone_name": "Billing Counter Queue", "zone_type": "BILLING", "is_revenue_zone": "Yes"},
]
AGE_BUCKETS = ["18-24", "25-34", "35-44", "45+"]
GENDERS = ["M", "F"]

start = datetime(2026, 3, 8, 10, 0, 0)
events = []
track_id = 100

for i in range(1, 51):
    id_token = f"ID_{60000+i}"
    gender = random.choice(GENDERS)
    age = random.randint(18, 55)
    age_bucket = "18-24" if age < 25 else "25-34" if age < 35 else "35-44" if age < 45 else "45+"
    group_id = f"G_{i//3}" if random.random() < 0.3 else None
    group_size = 2 if group_id else None
    entry_time = start + timedelta(seconds=random.randint(0, 3600))

    # Entry event
    events.append({
        "event_type": "entry",
        "id_token": id_token,
        "store_code": STORE_CODE,
        "camera_id": "cam1",
        "event_timestamp": entry_time.isoformat(),
        "is_staff": False,
        "gender_pred": gender,
        "age_pred": age,
        "age_bucket": age_bucket,
        "is_face_hidden": False,
        "group_id": group_id,
        "group_size": group_size
    })

    # Zone events
    track_id += 1
    for zone in random.sample(ZONES[:3], k=random.randint(1, 3)):
        zone_enter = entry_time + timedelta(seconds=random.randint(30, 300))
        zone_exit = zone_enter + timedelta(seconds=random.randint(30, 180))
        events.append({
            "event_type": "zone_entered", "track_id": track_id,
            "store_id": STORE_ID, "camera_id": "CAM2",
            "zone_id": zone["zone_id"], "zone_name": zone["zone_name"],
            "zone_type": zone["zone_type"], "is_revenue_zone": zone["is_revenue_zone"],
            "event_time": zone_enter.isoformat(),
            "zone_hotspot_x": round(random.uniform(100, 600), 1),
            "zone_hotspot_y": round(random.uniform(100, 400), 1),
            "gender": gender, "age": age, "age_bucket": age_bucket
        })
        events.append({
            "event_type": "zone_exited", "track_id": track_id,
            "store_id": STORE_ID, "camera_id": "CAM2",
            "zone_id": zone["zone_id"], "zone_name": zone["zone_name"],
            "zone_type": zone["zone_type"], "is_revenue_zone": zone["is_revenue_zone"],
            "event_time": zone_exit.isoformat(),
            "zone_hotspot_x": round(random.uniform(100, 600), 1),
            "zone_hotspot_y": round(random.uniform(100, 400), 1),
            "gender": gender, "age": age, "age_bucket": age_bucket
        })

    # Queue + exit for 40% of visitors
    if random.random() < 0.4:
        billing_zone = ZONES[3]
        queue_join = entry_time + timedelta(seconds=random.randint(600, 1800))
        abandoned = random.random() < 0.2
        events.append({
            "queue_event_id": str(uuid.uuid4()),
            "event_type": "queue_abandoned" if abandoned else "queue_completed",
            "track_id": track_id, "store_id": STORE_ID,
            "camera_id": "PURPLLE_MUM_1076_CAM6",
            "zone_id": billing_zone["zone_id"], "zone_name": billing_zone["zone_name"],
            "zone_type": "BILLING", "is_revenue_zone": "Yes",
            "queue_join_ts": queue_join.isoformat(),
            "queue_served_ts": None if abandoned else (queue_join + timedelta(seconds=random.randint(5,30))).isoformat(),
            "queue_exit_ts": (queue_join + timedelta(seconds=random.randint(30,120))).isoformat(),
            "wait_seconds": random.randint(5, 120),
            "queue_position_at_join": random.randint(1, 5),
            "abandoned": abandoned,
            "zone_hotspot_x": round(random.uniform(500, 650), 1),
            "zone_hotspot_y": round(random.uniform(150, 250), 1),
            "gender": gender, "age": age, "age_bucket": age_bucket
        })

    # Exit event
    exit_time = entry_time + timedelta(seconds=random.randint(900, 3600))
    events.append({
        "event_type": "exit",
        "id_token": id_token,
        "store_code": STORE_CODE,
        "camera_id": "cam1",
        "event_timestamp": exit_time.isoformat(),
        "is_staff": False,
        "gender_pred": gender,
        "age_pred": age,
        "age_bucket": age_bucket,
        "is_face_hidden": False,
        "group_id": group_id,
        "group_size": group_size
    })

events.sort(key=lambda x: x.get("event_timestamp") or x.get("event_time") or x.get("queue_join_ts", ""))
with open(output, "w") as f:
    for e in events:
        f.write(json.dumps(e) + "\n")
print(f"Generated {len(events)} events -> {output}")
