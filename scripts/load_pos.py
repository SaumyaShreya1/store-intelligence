"""Load POS transactions from CSV into the database."""
import csv, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.db import get_conn, init_db

def load_pos(csv_path="data/pos_transactions.csv"):
    init_db()
    conn = get_conn()
    loaded = skipped = 0
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                # Normalize timestamp
                ts = row["timestamp"].replace("Z", "")
                conn.execute("""
                    INSERT OR IGNORE INTO pos_transactions
                    (transaction_id, store_id, timestamp, basket_value)
                    VALUES (?, ?, ?, ?)
                """, (
                    row["transaction_id"],
                    row["store_id"],
                    ts,
                    float(row["basket_value_inr"])
                ))
                if conn.execute("SELECT changes()").fetchone()[0] == 0:
                    skipped += 1
                else:
                    loaded += 1
            except Exception as e:
                print(f"Error on row {row}: {e}")
                skipped += 1
    conn.commit()
    conn.close()
    print(f"POS transactions: {loaded} loaded, {skipped} skipped")

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "data/pos_transactions.csv"
    load_pos(path)
