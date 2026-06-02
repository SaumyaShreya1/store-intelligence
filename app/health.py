import time, json
from datetime import datetime, timezone
from fastapi import APIRouter
from app.models import HealthResponse, HealthStore
from app.db import get_conn

router = APIRouter()
START_TIME = time.time()

@router.get('/health', response_model=HealthResponse)
async def health():
    now = datetime.now(timezone.utc)
    conn = None
    try:
        conn = get_conn()
        rows = conn.execute('''
            SELECT store_id, MAX(timestamp) as last_event
            FROM events GROUP BY store_id
        ''').fetchall()

        stores = []
        for r in rows:
            lag = None
            status = 'OK'
            if r['last_event']:
                last_dt = datetime.strptime(
                    r['last_event'], '%Y-%m-%dT%H:%M:%SZ'
                ).replace(tzinfo=timezone.utc)
                lag = (now - last_dt).total_seconds()
                if lag > 600:
                    status = 'STALE_FEED'
            stores.append(HealthStore(
                store_id=r['store_id'],
                last_event_at=r['last_event'],
                status=status,
                lag_seconds=lag))

        overall = 'OK' if all(s.status == 'OK' for s in stores) else 'DEGRADED'
        return HealthResponse(
            status=overall,
            uptime_seconds=round(time.time() - START_TIME, 1),
            stores=stores,
            checked_at=now.strftime('%Y-%m-%dT%H:%M:%SZ'))
    except Exception as e:
        return HealthResponse(
            status='UNHEALTHY',
            uptime_seconds=round(time.time() - START_TIME, 1),
            stores=[],
            checked_at=now.strftime('%Y-%m-%dT%H:%M:%SZ'))
    finally:
        if conn:
            conn.close()
