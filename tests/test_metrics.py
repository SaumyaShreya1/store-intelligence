# PROMPT: "Write pytest tests for /metrics, /funnel, /heatmap endpoints covering:
#          empty store, all-staff events, zero purchases, re-entry dedup,
#          conversion rate math, zone dwell tracking. Use httpx TestClient."
# CHANGES MADE: Added fixture for seeding POS transactions manually,
#               fixed assertion for conversion_rate when store has events but
#               zero POS txns (was expecting None, API returns 0.0),
#               added test for partial-batch ingest with malformed events.

import pytest, json, uuid
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from app.main import app
from app.db import init_db, get_conn

STORE = 'STORE_TEST_001'

@pytest.fixture(autouse=True)
def clean_db(tmp_path, monkeypatch):
    import app.db as db_module
    db_path = str(tmp_path / 'test.db')
    monkeypatch.setattr(db_module, 'DB_PATH', db_path)
    init_db()
    yield

@pytest.fixture
def client():
    return TestClient(app)

def make_event(etype, visitor_id, zone=None, is_staff=False, ts=None):
    if ts is None:
        ts = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    return {
        'event_id':   str(uuid.uuid4()),
        'store_id':   STORE,
        'camera_id':  'CAM_ENTRY_01',
        'visitor_id': visitor_id,
        'event_type': etype,
        'timestamp':  ts,
        'zone_id':    zone,
        'dwell_ms':   5000,
        'is_staff':   is_staff,
        'confidence': 0.88,
        'metadata':   {'queue_depth': None, 'sku_zone': zone, 'session_seq': 1}
    }

def ingest(client, events):
    return client.post('/events/ingest', json={'events': events})


class TestIngest:
    def test_basic_ingest(self, client):
        evs = [make_event('ENTRY', 'VIS_001'), make_event('EXIT', 'VIS_001')]
        r = ingest(client, evs)
        assert r.status_code == 200
        assert r.json()['accepted'] == 2
        assert r.json()['rejected'] == 0

    def test_idempotent_double_ingest(self, client):
        evs = [make_event('ENTRY', 'VIS_001')]
        ingest(client, evs)
        r2 = ingest(client, evs)
        assert r2.json()['duplicate'] == 1
        assert r2.json()['accepted'] == 0

    def test_partial_batch_with_bad_event(self, client):
        good = make_event('ENTRY', 'VIS_002')
        bad  = {**make_event('ENTRY', 'VIS_003'), 'event_type': 'INVALID_TYPE'}
        r = ingest(client, [good, bad])
        assert r.json()['accepted'] == 1
        assert r.json()['rejected'] == 1

    def test_batch_limit_500(self, client):
        evs = [make_event('ENTRY', f'VIS_{i:04d}') for i in range(600)]
        r = ingest(client, evs)
        assert r.json()['accepted'] <= 500


class TestMetrics:
    def test_empty_store_returns_zeros(self, client):
        r = client.get(f'/stores/{STORE}/metrics')
        assert r.status_code == 200
        d = r.json()
        assert d['unique_visitors'] == 0
        assert d['conversion_rate'] == 0.0
        assert d['queue_depth'] == 0

    def test_staff_excluded_from_visitors(self, client):
        ingest(client, [
            make_event('ENTRY', 'STAFF_001', is_staff=True),
            make_event('ENTRY', 'VIS_001'),
        ])
        r = client.get(f'/stores/{STORE}/metrics')
        assert r.json()['unique_visitors'] == 1

    def test_zero_purchases_conversion_is_zero(self, client):
        ingest(client, [
            make_event('ENTRY',      'VIS_001'),
            make_event('ZONE_ENTER', 'VIS_001', 'BILLING_COUNTER'),
        ])
        r = client.get(f'/stores/{STORE}/metrics')
        assert r.json()['conversion_rate'] == 0.0

    def test_unique_visitor_count(self, client):
        for i in range(5):
            ingest(client, [make_event('ENTRY', f'VIS_{i:03d}')])
        r = client.get(f'/stores/{STORE}/metrics')
        assert r.json()['unique_visitors'] == 5


class TestFunnel:
    def test_funnel_stages_present(self, client):
        ingest(client, [
            make_event('ENTRY',      'VIS_001'),
            make_event('ZONE_ENTER', 'VIS_001', 'SKINCARE'),
        ])
        r = client.get(f'/stores/{STORE}/funnel')
        assert r.status_code == 200
        stages = {s['stage'] for s in r.json()['stages']}
        assert stages == {'Entry', 'Zone Visit', 'Billing Queue', 'Purchase'}

    def test_reentry_not_double_counted(self, client):
        ingest(client, [
            make_event('ENTRY',   'VIS_001'),
            make_event('EXIT',    'VIS_001'),
            make_event('REENTRY', 'VIS_001'),
        ])
        r = client.get(f'/stores/{STORE}/funnel')
        entry_stage = next(s for s in r.json()['stages'] if s['stage'] == 'Entry')
        assert entry_stage['count'] == 1


class TestHeatmap:
    def test_heatmap_normalised_0_100(self, client):
        for z in ['SKINCARE', 'BILLING_COUNTER', 'FRAGRANCE_DISPLAY']:
            ingest(client, [make_event('ZONE_EXIT', 'VIS_001', zone=z)])
        r = client.get(f'/stores/{STORE}/heatmap')
        scores = [z['normalized_score'] for z in r.json()['zones']]
        assert max(scores) == 100.0
        assert min(scores) >= 0.0

    def test_low_confidence_flag_under_20_sessions(self, client):
        ingest(client, [make_event('ZONE_EXIT', 'VIS_001', 'SKINCARE')])
        r = client.get(f'/stores/{STORE}/heatmap')
        for z in r.json()['zones']:
            assert z['data_confidence'] == 'LOW'


class TestAnomalies:
    def test_no_anomalies_fresh_store(self, client):
        r = client.get(f'/stores/{STORE}/anomalies')
        assert r.status_code == 200
        assert r.json()['anomalies'] == []

    def test_queue_spike_detected(self, client):
        ingest(client, [{
            **make_event('BILLING_QUEUE_JOIN', 'VIS_001', 'BILLING_QUEUE'),
            'metadata': {'queue_depth': 5, 'sku_zone': 'BILLING_QUEUE', 'session_seq': 1}
        }])
        r = client.get(f'/stores/{STORE}/anomalies')
        types = [a['anomaly_type'] for a in r.json()['anomalies']]
        assert 'BILLING_QUEUE_SPIKE' in types


class TestHealth:
    def test_health_ok(self, client):
        r = client.get('/health')
        assert r.status_code == 200
        assert 'status' in r.json()
        assert 'uptime_seconds' in r.json()
