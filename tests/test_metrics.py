# PROMPT: "Write pytest tests for /metrics, /funnel, /heatmap, /anomalies, /health
#          endpoints covering: empty store, all-staff events, zero purchases,
#          re-entry dedup, conversion rate math, zone dwell tracking, queue
#          abandonment, gender/age breakdown. Use httpx TestClient with the
#          actual Purplle sample event schema (entry/exit with id_token,
#          zone_entered/zone_exited, queue_completed/queue_abandoned)."
# CHANGES MADE:
#   - Updated event factory to use new schema fields (id_token, store_code,
#     event_timestamp, gender_pred, age_pred, age_bucket, group_id)
#   - Added zone event factory for zone_entered/zone_exited events
#   - Added queue event factory for queue_completed/queue_abandoned events
#   - Fixed staff exclusion test to use is_staff=True in new schema
#   - Added gender_breakdown and age_breakdown assertions to metrics tests
#   - Updated event_type values to lowercase (entry/exit not ENTRY/EXIT)

import pytest, json, uuid
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from app.main import app
from app.db import init_db, get_conn

STORE = "store_1076"
STORE_ID = "ST1076"

@pytest.fixture(autouse=True)
def clean_db(tmp_path, monkeypatch):
    import app.db as db_module
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    init_db()
    yield

@pytest.fixture
def client():
    return TestClient(app)

def ts():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

def make_entry(id_token, is_staff=False, gender="F", age=28, group_id=None):
    return {
        "event_type": "entry",
        "id_token": id_token,
        "store_code": STORE,
        "camera_id": "cam1",
        "event_timestamp": ts(),
        "is_staff": is_staff,
        "gender_pred": gender,
        "age_pred": age,
        "age_bucket": "25-34",
        "is_face_hidden": False,
        "group_id": group_id,
        "group_size": 2 if group_id else None
    }

def make_exit(id_token, gender="F", age=28):
    return {
        "event_type": "exit",
        "id_token": id_token,
        "store_code": STORE,
        "camera_id": "cam1",
        "event_timestamp": ts(),
        "is_staff": False,
        "gender_pred": gender,
        "age_pred": age,
        "age_bucket": "25-34",
        "is_face_hidden": False,
        "group_id": None,
        "group_size": None
    }

def make_zone(track_id, zone_id, zone_name, event_type="zone_entered",
              zone_type="SHELF", gender="F", age=28):
    return {
        "event_type": event_type,
        "track_id": track_id,
        "store_id": STORE_ID,
        "camera_id": "CAM2",
        "zone_id": zone_id,
        "zone_name": zone_name,
        "zone_type": zone_type,
        "is_revenue_zone": "Yes",
        "event_time": ts(),
        "zone_hotspot_x": 300.0,
        "zone_hotspot_y": 200.0,
        "gender": gender,
        "age": age,
        "age_bucket": "25-34"
    }

def make_queue(track_id, abandoned=False, gender="F", age=28):
    return {
        "queue_event_id": str(uuid.uuid4()),
        "event_type": "queue_abandoned" if abandoned else "queue_completed",
        "track_id": track_id,
        "store_id": STORE_ID,
        "camera_id": "PURPLLE_MUM_1076_CAM6",
        "zone_id": "PURPLLE_MUM_1076_Z_BILLING_01",
        "zone_name": "Billing Counter Queue",
        "zone_type": "BILLING",
        "is_revenue_zone": "Yes",
        "queue_join_ts": ts(),
        "queue_served_ts": None if abandoned else ts(),
        "queue_exit_ts": ts(),
        "wait_seconds": 60 if abandoned else 15,
        "queue_position_at_join": 2,
        "abandoned": abandoned,
        "zone_hotspot_x": 600.0,
        "zone_hotspot_y": 180.0,
        "gender": gender,
        "age": age,
        "age_bucket": "25-34"
    }

def ingest(client, events):
    return client.post("/events/ingest", json={"events": events})


class TestIngest:
    def test_basic_ingest(self, client):
        r = ingest(client, [make_entry("ID_001"), make_exit("ID_001")])
        assert r.status_code == 200
        assert r.json()["accepted"] == 2
        assert r.json()["rejected"] == 0

    def test_idempotent_double_ingest(self, client):
        evs = [make_entry("ID_001")]
        ingest(client, evs)
        r2 = ingest(client, evs)
        assert r2.json()["duplicate"] == 1
        assert r2.json()["accepted"] == 0

    def test_partial_batch_with_bad_event(self, client):
        good = make_entry("ID_002")
        bad = {**make_entry("ID_003"), "event_type": "INVALID_TYPE"}
        r = ingest(client, [good, bad])
        assert r.json()["accepted"] == 1
        assert r.json()["rejected"] == 1

    def test_batch_limit_500(self, client):
        evs = [make_entry(f"ID_{i:04d}") for i in range(600)]
        r = ingest(client, evs)
        assert r.json()["accepted"] <= 500

    def test_zone_events_accepted(self, client):
        r = ingest(client, [
            make_zone(101, "PURPLLE_MUM_1076_Z01", "Left Shelf", "zone_entered"),
            make_zone(101, "PURPLLE_MUM_1076_Z01", "Left Shelf", "zone_exited"),
        ])
        assert r.json()["accepted"] == 2

    def test_queue_events_accepted(self, client):
        r = ingest(client, [make_queue(101), make_queue(102, abandoned=True)])
        assert r.json()["accepted"] == 2


class TestMetrics:
    def test_empty_store_returns_zeros(self, client):
        r = client.get(f"/stores/{STORE}/metrics")
        assert r.status_code == 200
        d = r.json()
        assert d["unique_visitors"] == 0
        assert d["conversion_rate"] == 0.0
        assert d["queue_depth"] == 0

    def test_staff_excluded_from_visitors(self, client):
        ingest(client, [
            make_entry("STAFF_001", is_staff=True),
            make_entry("ID_001"),
        ])
        r = client.get(f"/stores/{STORE}/metrics")
        assert r.json()["unique_visitors"] == 1

    def test_zero_purchases_conversion_is_zero(self, client):
        ingest(client, [make_entry("ID_001")])
        r = client.get(f"/stores/{STORE}/metrics")
        assert r.json()["conversion_rate"] == 0.0

    def test_unique_visitor_count(self, client):
        for i in range(5):
            ingest(client, [make_entry(f"ID_{i:03d}")])
        r = client.get(f"/stores/{STORE}/metrics")
        assert r.json()["unique_visitors"] == 5

    def test_gender_breakdown_present(self, client):
        ingest(client, [
            make_entry("ID_001", gender="F"),
            make_entry("ID_002", gender="M"),
        ])
        r = client.get(f"/stores/{STORE}/metrics")
        assert "gender_breakdown" in r.json()

    def test_age_breakdown_present(self, client):
        ingest(client, [make_entry("ID_001", age=28)])
        r = client.get(f"/stores/{STORE}/metrics")
        assert "age_breakdown" in r.json()

    def test_abandonment_rate(self, client):
        ingest(client, [
            make_queue(101, abandoned=True),
            make_queue(102, abandoned=False),
        ])
        r = client.get(f"/stores/{STORE_ID}/metrics")
        assert r.json()["abandonment_rate"] == 0.5


class TestFunnel:
    def test_funnel_stages_present(self, client):
        ingest(client, [
            make_entry("ID_001"),
            make_zone(101, "PURPLLE_MUM_1076_Z01", "Left Shelf", "zone_entered"),
        ])
        r = client.get(f"/stores/{STORE}/funnel")
        assert r.status_code == 200
        stages = {s["stage"] for s in r.json()["stages"]}
        assert stages == {"Entry", "Zone Visit", "Billing Queue", "Purchase"}

    def test_reentry_not_double_counted(self, client):
        ingest(client, [
            make_entry("ID_001"),
            make_exit("ID_001"),
            make_entry("ID_001"),
        ])
        r = client.get(f"/stores/{STORE}/funnel")
        entry_stage = next(s for s in r.json()["stages"] if s["stage"] == "Entry")
        assert entry_stage["count"] == 1


class TestHeatmap:
    def test_heatmap_normalised_0_100(self, client):
        for zone in ["Z01", "Z02", "Z03"]:
            ingest(client, [make_zone(101, f"PURPLLE_MUM_1076_{zone}",
                                     zone, "zone_exited")])
        r = client.get(f"/stores/{STORE_ID}/heatmap")
        scores = [z["normalized_score"] for z in r.json()["zones"]]
        assert max(scores) == 100.0
        assert min(scores) >= 0.0

    def test_low_confidence_flag_under_20_sessions(self, client):
        ingest(client, [make_zone(101, "PURPLLE_MUM_1076_Z01",
                                  "Left Shelf", "zone_exited")])
        r = client.get(f"/stores/{STORE_ID}/heatmap")
        for z in r.json()["zones"]:
            assert z["data_confidence"] == "LOW"


class TestAnomalies:
    def test_no_anomalies_fresh_store(self, client):
        r = client.get(f"/stores/{STORE}/anomalies")
        assert r.status_code == 200
        assert r.json()["anomalies"] == []

    def test_queue_spike_detected(self, client):
        for i in range(6):
            ingest(client, [make_queue(100+i)])
        r = client.get(f"/stores/{STORE_ID}/anomalies")
        types = [a["anomaly_type"] for a in r.json()["anomalies"]]
        assert "BILLING_QUEUE_SPIKE" in types


class TestHealth:
    def test_health_ok(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert "status" in r.json()
        assert "uptime_seconds" in r.json()
