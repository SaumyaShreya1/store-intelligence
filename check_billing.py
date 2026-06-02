
import json
events = [json.loads(l) for l in open("data/events_all.jsonl")]
billing = [e for e in events if e.get("zone_id") and "BILLING" in e.get("zone_id","") and not e.get("is_staff")]
print("Found", len(billing), "billing events")
for e in billing[:5]:
    print(" ", e["timestamp"], "visitor=", e["visitor_id"])

