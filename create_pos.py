
import json, csv, uuid, os
from datetime import datetime, timedelta, timezone

events = [json.loads(l) for l in open("data/events_all.jsonl")]

billing = [e for e in events 
           if e.get("zone_id") and "BILLING" in e.get("zone_id","") 
           and not e.get("is_staff")]

# Get unique visitors in billing zone
billing_visitors = {}
for e in billing:
    vid = e["visitor_id"]
    if vid not in billing_visitors:
        billing_visitors[vid] = e["timestamp"]

print(f"Unique billing visitors: {len(billing_visitors)}")

# Convert 40% of billing visitors to purchases
import random
random.seed(42)
all_visitors = list(billing_visitors.items())
converted = random.sample(all_visitors, int(len(all_visitors) * 0.4))

print(f"Converting {len(converted)} visitors to purchases")

# Create POS transactions - transaction happens 2 minutes after billing entry
transactions = []
for i, (vid, ts) in enumerate(converted):
    txn_time = (datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                + timedelta(minutes=2))
    transactions.append({
        "transaction_id": f"TXN_{i+1:05d}",
        "store_id": "STORE_PURPLLE_001",
        "timestamp": txn_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "basket_value_inr": round(random.uniform(400, 3500), 2)
    })

# Save as CSV
os.makedirs("data", exist_ok=True)
with open("data/pos_transactions.csv", "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["transaction_id","store_id","timestamp","basket_value_inr"])
    writer.writeheader()
    writer.writerows(transactions)

print(f"Saved {len(transactions)} POS transactions to data/pos_transactions.csv")
print("Sample:")
for t in transactions[:3]:
    print(" ", t)

