import sqlite3, os

DB_PATH = os.environ.get("DATABASE_URL", "sqlite:///data/store.db").replace("sqlite:///", "")

def get_conn():
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS events (
            event_id      TEXT PRIMARY KEY,
            store_id      TEXT NOT NULL,
            camera_id     TEXT NOT NULL,
            visitor_id    TEXT NOT NULL,
            event_type    TEXT NOT NULL,
            timestamp     TEXT NOT NULL,
            zone_id       TEXT,
            zone_name     TEXT,
            zone_type     TEXT,
            is_revenue_zone TEXT,
            dwell_ms      INTEGER DEFAULT 0,
            is_staff      INTEGER DEFAULT 0,
            confidence    REAL DEFAULT 1.0,
            queue_depth   INTEGER,
            abandoned     INTEGER DEFAULT 0,
            gender        TEXT,
            age           INTEGER,
            age_bucket    TEXT,
            group_id      TEXT,
            group_size    INTEGER,
            is_face_hidden INTEGER DEFAULT 0,
            raw_json      TEXT,
            ingested_at   TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_store_ts
            ON events(store_id, timestamp);
        CREATE INDEX IF NOT EXISTS idx_visitor
            ON events(visitor_id);
        CREATE INDEX IF NOT EXISTS idx_type
            ON events(event_type);
        CREATE INDEX IF NOT EXISTS idx_zone
            ON events(store_id, zone_id);
        CREATE INDEX IF NOT EXISTS idx_gender
            ON events(store_id, gender);
        CREATE INDEX IF NOT EXISTS idx_age_bucket
            ON events(store_id, age_bucket);

        CREATE TABLE IF NOT EXISTS pos_transactions (
            transaction_id  TEXT PRIMARY KEY,
            store_id        TEXT NOT NULL,
            timestamp       TEXT NOT NULL,
            basket_value    REAL NOT NULL,
            product_id      TEXT,
            brand_name      TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_pos_store
            ON pos_transactions(store_id, timestamp);
    """)
    conn.close()
