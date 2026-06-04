import uuid, json, logging
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Request, HTTPException
from app.models import StoreMetrics, ZoneMetric, StoreFunnel, FunnelStage, StoreHeatmap, HeatmapZone
from app.db import get_conn

router = APIRouter()
log = logging.getLogger("metrics")

def _cutoff(window_minutes=480):
    if window_minutes >= 999999:
        return "2000-01-01T00:00:00"
    return (datetime.now(timezone.utc) - timedelta(minutes=window_minutes)).strftime("%Y-%m-%dT%H:%M:%S")

def _norm_ts(ts):
    """Normalize timestamp for comparison - strip Z suffix."""
    return ts.replace("Z", "") if ts else ""

@router.get("/stores/{store_id}/metrics", response_model=StoreMetrics)
async def get_metrics(store_id: str, window_minutes: int = 480, request: Request = None):
    trace_id = (request.headers.get("X-Trace-Id") if request else None) or str(uuid.uuid4())
    start = datetime.now(timezone.utc)
    conn = get_conn()
    try:
        cutoff = _cutoff(window_minutes)

        # Unique visitors from entry events (exclude staff)
        row = conn.execute("""
            SELECT COUNT(DISTINCT visitor_id) as cnt FROM events
            WHERE store_id=? AND event_type='entry'
            AND is_staff=0 AND timestamp>=?
        """, (store_id, cutoff)).fetchone()
        unique_visitors = row["cnt"] if row else 0

        # POS-based conversion
        txns = conn.execute("""
            SELECT timestamp FROM pos_transactions
            WHERE store_id=? AND timestamp>=? ORDER BY timestamp
        """, (store_id, cutoff)).fetchall()

        converted = set()
        for txn in txns:
            ts = _norm_ts(txn["timestamp"])
            win_start = (datetime.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S")
                         - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S")
            rows = conn.execute("""
                SELECT DISTINCT visitor_id FROM events
                WHERE store_id=? AND zone_type='BILLING'
                AND is_staff=0 AND timestamp BETWEEN ? AND ?
            """, (store_id, win_start, ts)).fetchall()
            for r in rows:
                converted.add(r["visitor_id"])

        conversion_rate = len(converted) / unique_visitors if unique_visitors > 0 else 0.0

        # Average dwell from zone_exited events
        row = conn.execute("""
            SELECT AVG(dwell_ms) as avg FROM events
            WHERE store_id=? AND event_type='zone_exited'
            AND is_staff=0 AND timestamp>=?
        """, (store_id, cutoff)).fetchone()
        avg_dwell = row["avg"] or 0.0

        # Current queue depth
        row = conn.execute("""
            SELECT queue_depth FROM events
            WHERE store_id=? AND event_type='queue_completed'
            ORDER BY timestamp DESC LIMIT 1
        """, (store_id,)).fetchone()
        queue_depth = row["queue_depth"] or 0 if row else 0

        # Abandonment rate
        ab_row = conn.execute("""
            SELECT COUNT(DISTINCT visitor_id) as cnt FROM events
            WHERE store_id=? AND event_type='queue_abandoned'
            AND is_staff=0 AND timestamp>=?
        """, (store_id, cutoff)).fetchone()
        joins_row = conn.execute("""
            SELECT COUNT(DISTINCT visitor_id) as cnt FROM events
            WHERE store_id=? AND event_type IN ('queue_completed','queue_abandoned')
            AND is_staff=0 AND timestamp>=?
        """, (store_id, cutoff)).fetchone()
        ab_cnt = ab_row["cnt"] if ab_row else 0
        join_cnt = joins_row["cnt"] if joins_row else 0
        abandonment_rate = ab_cnt / join_cnt if join_cnt > 0 else 0.0

        # Zone metrics
        zone_rows = conn.execute("""
            SELECT zone_id, zone_name,
                   is_revenue_zone,
                   COUNT(DISTINCT visitor_id) as visits,
                   AVG(dwell_ms) as avg_dwell
            FROM events
            WHERE store_id=? AND zone_id IS NOT NULL
            AND is_staff=0 AND timestamp>=?
            AND event_type='zone_exited'
            GROUP BY zone_id
        """, (store_id, cutoff)).fetchall()

        zones = [ZoneMetric(
            zone_id=r["zone_id"],
            zone_name=r["zone_name"] or "",
            visit_count=r["visits"],
            avg_dwell_ms=round(r["avg_dwell"] or 0.0, 1),
            is_revenue_zone=(r["is_revenue_zone"] == "Yes")
        ) for r in zone_rows]

        if zones:
            max_v = max(z.visit_count for z in zones) or 1
            for z in zones:
                z.normalized_score = round(z.visit_count / max_v * 100, 1)

        # Gender breakdown
        gender_rows = conn.execute("""
            SELECT gender, COUNT(DISTINCT visitor_id) as cnt FROM events
            WHERE store_id=? AND event_type='entry'
            AND is_staff=0 AND timestamp>=? AND gender IS NOT NULL
            GROUP BY gender
        """, (store_id, cutoff)).fetchall()
        gender_breakdown = {r["gender"]: r["cnt"] for r in gender_rows}

        # Age breakdown
        age_rows = conn.execute("""
            SELECT age_bucket, COUNT(DISTINCT visitor_id) as cnt FROM events
            WHERE store_id=? AND event_type='entry'
            AND is_staff=0 AND timestamp>=? AND age_bucket IS NOT NULL
            GROUP BY age_bucket
        """, (store_id, cutoff)).fetchall()
        age_breakdown = {r["age_bucket"]: r["cnt"] for r in age_rows}

        confidence = "LOW" if unique_visitors < 10 else "MEDIUM" if unique_visitors < 20 else "HIGH"

        ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
        log.info(json.dumps({
            "trace_id": trace_id,
            "endpoint": f"/stores/{store_id}/metrics",
            "latency_ms": round(ms, 2),
            "status_code": 200
        }))
        return StoreMetrics(
            store_id=store_id,
            unique_visitors=unique_visitors,
            conversion_rate=round(conversion_rate, 4),
            avg_dwell_ms=round(avg_dwell, 1),
            queue_depth=queue_depth,
            abandonment_rate=round(abandonment_rate, 4),
            zones=zones,
            window_minutes=window_minutes,
            data_confidence=confidence,
            gender_breakdown=gender_breakdown,
            age_breakdown=age_breakdown
        )
    except Exception as e:
        raise HTTPException(503, detail={"error": str(e), "type": "DATABASE_ERROR"})
    finally:
        conn.close()


@router.get("/stores/{store_id}/funnel", response_model=StoreFunnel)
async def get_funnel(store_id: str, window_minutes: int = 480):
    conn = get_conn()
    try:
        cutoff = _cutoff(window_minutes)

        entry_vis = set(r["visitor_id"] for r in conn.execute("""
            SELECT DISTINCT visitor_id FROM events
            WHERE store_id=? AND event_type='entry'
            AND is_staff=0 AND timestamp>=?
        """, (store_id, cutoff)).fetchall())

        zone_vis = set(r["visitor_id"] for r in conn.execute("""
            SELECT DISTINCT visitor_id FROM events
            WHERE store_id=? AND event_type='zone_entered'
            AND is_staff=0 AND timestamp>=?
        """, (store_id, cutoff)).fetchall()) & entry_vis

        billing_vis = set(r["visitor_id"] for r in conn.execute("""
            SELECT DISTINCT visitor_id FROM events
            WHERE store_id=? AND zone_type='BILLING'
            AND is_staff=0 AND timestamp>=?
        """, (store_id, cutoff)).fetchall()) & entry_vis

        txns = conn.execute("""
            SELECT timestamp FROM pos_transactions
            WHERE store_id=? AND timestamp>=?
        """, (store_id, cutoff)).fetchall()

        purchased_vis = set()
        for txn in txns:
            ts = _norm_ts(txn["timestamp"])
            win = (datetime.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S")
                   - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S")
            for r in conn.execute("""
                SELECT DISTINCT visitor_id FROM events
                WHERE store_id=? AND zone_type='BILLING'
                AND is_staff=0 AND timestamp BETWEEN ? AND ?
            """, (store_id, win, ts)).fetchall():
                purchased_vis.add(r["visitor_id"])
        purchased_vis &= entry_vis

        def pct(a, b): return round((1 - a / b) * 100, 1) if b > 0 and a < b else 0.0

        e, z, b, p = len(entry_vis), len(zone_vis), len(billing_vis), len(purchased_vis)
        stages = [
            FunnelStage(stage="Entry",         count=e, drop_off_pct=0.0),
            FunnelStage(stage="Zone Visit",    count=z, drop_off_pct=pct(z, e)),
            FunnelStage(stage="Billing Queue", count=b, drop_off_pct=pct(b, z)),
            FunnelStage(stage="Purchase",      count=p, drop_off_pct=pct(p, b)),
        ]
        return StoreFunnel(store_id=store_id, stages=stages)
    finally:
        conn.close()


@router.get("/stores/{store_id}/heatmap", response_model=StoreHeatmap)
async def get_heatmap(store_id: str, window_minutes: int = 480):
    conn = get_conn()
    try:
        cutoff = _cutoff(window_minutes)
        rows = conn.execute("""
            SELECT zone_id, zone_name,
                   COUNT(DISTINCT visitor_id) as visits,
                   AVG(dwell_ms) as avg_dwell
            FROM events
            WHERE store_id=? AND zone_id IS NOT NULL
            AND is_staff=0 AND timestamp>=?
            GROUP BY zone_id
        """, (store_id, cutoff)).fetchall()

        session_count = conn.execute("""
            SELECT COUNT(DISTINCT visitor_id) FROM events
            WHERE store_id=? AND event_type='entry'
            AND is_staff=0 AND timestamp>=?
        """, (store_id, cutoff)).fetchone()[0] or 0

        zones = []
        if rows:
            max_v = max(r["visits"] for r in rows) or 1
            for r in rows:
                conf = "LOW" if session_count < 20 else "HIGH"
                zones.append(HeatmapZone(
                    zone_id=r["zone_id"],
                    zone_name=r["zone_name"] or "",
                    visit_count=r["visits"],
                    avg_dwell_ms=round(r["avg_dwell"] or 0.0, 1),
                    normalized_score=round(r["visits"] / max_v * 100, 1),
                    data_confidence=conf
                ))
        return StoreHeatmap(store_id=store_id, zones=zones)
    finally:
        conn.close()
