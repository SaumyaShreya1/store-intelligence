
import csv, sys
sys.path.insert(0, ".")
from app.db import get_conn

conn = get_conn()
loaded = 0
with open("data/pos_transactions.csv") as f:
    reader = csv.DictReader(f)
    for row in reader:
        conn.execute(
            "INSERT OR IGNORE INTO pos_transactions (transaction_id, store_id, timestamp, basket_value) VALUES (?,?,?,?)",
            (row["transaction_id"], row["store_id"], row["timestamp"], float(row["basket_value_inr"]))
        )
        loaded += 1
conn.commit()
conn.close()
print(f"Loaded {loaded} POS transactions into database")

