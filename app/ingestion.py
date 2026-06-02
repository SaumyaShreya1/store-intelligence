import uuid, logging, json
from datetime import datetime, timezone
from fastapi import APIRouter, Request
from app.models import IngestRequest, IngestResponse
from app.db import get_conn

router = APIRouter()
log = logging.getLogger('ingestion')

VALID_EVENT_TYPES = {
    'ENTRY','EXIT','ZONE_ENTER','ZONE_EXIT','ZONE_DWELL',
    'BILLING_QUEUE_JOIN','BILLING_QUEUE_ABANDON','REENTRY'
}

def _validate(ev):
    if ev.event_type not in VALID_EVENT_TYPES:
        return f'unknown event_type: {ev.event_type}'
    try:
        datetime.strptime(ev.timestamp, '%Y-%m-%dT%H:%M:%SZ')
    except ValueError:
        return f'bad timestamp: {ev.timestamp}'
    if not ev.visitor_id or not ev.store_id:
        return 'missing visitor_id or store_id'
    return None


@router.post('/events/ingest', response_model=IngestResponse)
async def ingest_events(req: IngestRequest, request: Request):
    trace_id = request.headers.get('X-Trace-Id', str(uuid.uuid4()))
    start = datetime.now(timezone.utc)
    accepted = rejected = duplicate = 0
    errors = []
    conn = get_conn()
    try:
        for ev in req.events[:500]:
            err = _validate(ev)
            if err:
                rejected += 1
                errors.append({'event_id': ev.event_id, 'reason': err})
                continue
            try:
                conn.execute('''
                    INSERT OR IGNORE INTO events
                    (event_id,store_id,camera_id,visitor_id,event_type,timestamp,
                     zone_id,dwell_ms,is_staff,confidence,queue_depth,sku_zone,session_seq)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                ''', (ev.event_id, ev.store_id, ev.camera_id, ev.visitor_id,
                      ev.event_type, ev.timestamp, ev.zone_id, ev.dwell_ms,
                      int(ev.is_staff), ev.confidence,
                      ev.metadata.queue_depth, ev.metadata.sku_zone,
                      ev.metadata.session_seq))
                if conn.execute('SELECT changes()').fetchone()[0] == 0:
                    duplicate += 1
                else:
                    accepted += 1
            except Exception as e:
                rejected += 1
                errors.append({'event_id': ev.event_id, 'reason': str(e)})
        conn.commit()
    finally:
        conn.close()
    ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
    log.info(json.dumps({'trace_id': trace_id, 'endpoint': '/events/ingest',
                         'accepted': accepted, 'rejected': rejected,
                         'duplicate': duplicate, 'latency_ms': round(ms, 2),
                         'status_code': 200}))
    return IngestResponse(accepted=accepted, rejected=rejected,
                          duplicate=duplicate, errors=errors)
