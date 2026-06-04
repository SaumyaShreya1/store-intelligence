import uuid, json
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, HTTPException
from app.models import Anomaly
from app.db import get_conn

router = APIRouter()


@router.get("/stores/{store_id}/anomalies")
async def get_anomalies(store_id: str):
    conn = get_conn()
    try:
        now = datetime.now(timezone.utc)
        anomalies = []

        def ts():
            return now.strftime("%Y-%m-%dT%H:%M:%S")

        cutoff_5min = (now - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S")
        row = conn.execute("""
            SELECT COUNT(*) as cnt FROM events
            WHERE store_id=? AND event_type IN ('queue_completed','queue_abandoned','BILLING_QUEUE_JOIN')
            AND timestamp>=?
        """, (store_id, cutoff_5min)).fetchone()
        if row and row["cnt"] and row["cnt"] > 3:
            anomalies.append(Anomaly(
                anomaly_id=str(uuid.uuid4()), store_id=store_id,
                anomaly_type="BILLING_QUEUE_SPIKE", severity="WARN",
                zone_id="PURPLLE_MUM_1076_Z_BILLING_01",
                description=f"Queue depth {row['cnt']} exceeds threshold of 3 in last 5 minutes",
                suggested_action="Deploy additional staff to billing counter immediately",
                detected_at=ts()))

        cur_window = (now - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S")
        old_window = (now - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S")
        old_end    = cur_window

        cur_entry = conn.execute("""
            SELECT COUNT(DISTINCT visitor_id) FROM events
            WHERE store_id=? AND event_type IN ('entry','ENTRY')
            AND is_staff=0 AND timestamp>=?
        """, (store_id, cur_window)).fetchone()[0] or 0

        cur_billing = conn.execute("""
            SELECT COUNT(DISTINCT visitor_id) FROM events
            WHERE store_id=? AND (zone_type='BILLING' OR zone_id LIKE '%BILLING%')
            AND is_staff=0 AND timestamp>=?
        """, (store_id, cur_window)).fetchone()[0] or 0

        hist_entry = conn.execute("""
            SELECT COUNT(DISTINCT visitor_id) FROM events
            WHERE store_id=? AND event_type IN ('entry','ENTRY')
            AND is_staff=0 AND timestamp BETWEEN ? AND ?
        """, (store_id, old_window, old_end)).fetchone()[0] or 0

        hist_billing = conn.execute("""
            SELECT COUNT(DISTINCT visitor_id) FROM events
            WHERE store_id=? AND (zone_type='BILLING' OR zone_id LIKE '%BILLING%')
            AND is_staff=0 AND timestamp BETWEEN ? AND ?
        """, (store_id, old_window, old_end)).fetchone()[0] or 0

        cur_conv  = cur_billing  / cur_entry  if cur_entry  > 0 else None
        hist_conv = hist_billing / hist_entry if hist_entry > 0 else None

        if cur_conv is not None and hist_conv is not None:
            drop = (hist_conv - cur_conv) / hist_conv
            if drop > 0.25:
                anomalies.append(Anomaly(
                    anomaly_id=str(uuid.uuid4()), store_id=store_id,
                    anomaly_type="CONVERSION_DROP", severity="CRITICAL",
                    description=f"Conversion {cur_conv:.1%} is {drop:.0%} below 7-day avg {hist_conv:.1%}",
                    suggested_action="Review product placement and staff engagement in floor zones",
                    detected_at=ts()))

        dead_cutoff = (now - timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%S")
        zone_rows = conn.execute("""
            SELECT zone_id, MAX(timestamp) as last_visit FROM events
            WHERE store_id=? AND zone_id IS NOT NULL AND is_staff=0
            GROUP BY zone_id
        """, (store_id,)).fetchall()

        for r in zone_rows:
            if r["last_visit"] and r["last_visit"] < dead_cutoff:
                anomalies.append(Anomaly(
                    anomaly_id=str(uuid.uuid4()), store_id=store_id,
                    anomaly_type="DEAD_ZONE", severity="INFO",
                    zone_id=r["zone_id"],
                    description=f"No customer visits in {r['zone_id']} for 30+ minutes",
                    suggested_action=f"Check {r['zone_id']} display and lighting",
                    detected_at=ts()))

        last_ev = conn.execute("""
            SELECT MAX(timestamp) as last FROM events
            WHERE store_id=? AND is_staff=0
        """, (store_id,)).fetchone()
        empty_cutoff = (now - timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M:%S")
        if last_ev and last_ev["last"] and last_ev["last"] < empty_cutoff:
            anomalies.append(Anomaly(
                anomaly_id=str(uuid.uuid4()), store_id=store_id,
                anomaly_type="EMPTY_STORE", severity="INFO",
                description="No customer activity detected in 15+ minutes",
                suggested_action="Verify store is open and check entry camera feed",
                detected_at=ts()))

        return {"store_id": store_id,
                "anomalies": [a.model_dump() for a in anomalies],
                "checked_at": ts()}
    except Exception as e:
        raise HTTPException(503, detail={"error": str(e), "type": "DATABASE_ERROR"})
    finally:
        conn.close()
