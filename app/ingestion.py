import uuid, logging, json, hashlib
from datetime import datetime, timezone
from fastapi import APIRouter, Request
from app.models import IngestRequest, IngestResponse
from app.db import get_conn

router = APIRouter()
log = logging.getLogger("ingestion")

ENTRY_EXIT_TYPES = {"entry", "exit"}
ZONE_TYPES = {"zone_entered", "zone_exited"}
QUEUE_TYPES = {"queue_completed", "queue_abandoned"}
ALL_VALID_TYPES = ENTRY_EXIT_TYPES | ZONE_TYPES | QUEUE_TYPES

def _get_store_id(ev: dict) -> str:
    return ev.get("store_id") or ev.get("store_code") or ""

def _get_timestamp(ev: dict) -> str:
    return (ev.get("event_timestamp") or ev.get("event_time") or
            ev.get("queue_join_ts") or "")

def _get_visitor_id(ev: dict) -> str:
    return str(ev.get("id_token") or ev.get("track_id") or "")

def _validate(ev: dict) -> str:
    et = ev.get("event_type", "")
    if et not in ALL_VALID_TYPES:
        return f"unknown event_type: {et}"
    if not _get_store_id(ev):
        return "missing store_id or store_code"
    if not _get_timestamp(ev):
        return "missing timestamp field"
    return None

@router.post("/events/ingest", response_model=IngestResponse)
async def ingest_events(req: IngestRequest, request: Request):
    trace_id = request.headers.get("X-Trace-Id", str(uuid.uuid4()))
    start = datetime.now(timezone.utc)
    accepted = rejected = duplicate = 0
    errors = []
    conn = get_conn()
    try:
        for ev in req.events[:500]:
            err = _validate(ev)
            if err:
                rejected += 1
                errors.append({"reason": err, "event": str(ev)[:100]})
                continue
            event_type = ev.get("event_type")
            store_id = _get_store_id(ev)
            visitor_id = _get_visitor_id(ev)
            timestamp = _get_timestamp(ev)
            import hashlib`n            raw_key = f"{ev.get(chr(39)event_type{chr(39))}:{_get_store_id(ev)}:{_get_visitor_id(ev)}:{_get_timestamp(ev)}"`n            event_id = ev.get("queue_event_id") or hashlib.md5(raw_key.encode()).hexdigest()
            try:
                if event_type in ENTRY_EXIT_TYPES:
                    conn.execute("""
                        INSERT OR IGNORE INTO events
                        (event_id, store_id, camera_id, visitor_id, event_type,
                         timestamp, zone_id, dwell_ms, is_staff, confidence,
                         gender, age, age_bucket, group_id, group_size,
                         is_face_hidden, raw_json)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (event_id, store_id,
                          ev.get("camera_id", ""),
                          visitor_id, event_type, timestamp,
                          None, 0,
                          int(ev.get("is_staff", False)),
                          1.0,
                          ev.get("gender_pred"),
                          ev.get("age_pred"),
                          ev.get("age_bucket"),
                          ev.get("group_id"),
                          ev.get("group_size"),
                          int(ev.get("is_face_hidden", False)),
                          json.dumps(ev)))

                elif event_type in ZONE_TYPES:
                    dwell_ms = 0
                    conn.execute("""
                        INSERT OR IGNORE INTO events
                        (event_id, store_id, camera_id, visitor_id, event_type,
                         timestamp, zone_id, zone_name, zone_type,
                         is_revenue_zone, dwell_ms, is_staff, confidence,
                         gender, age, age_bucket, raw_json)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (event_id, store_id,
                          ev.get("camera_id", ""),
                          visitor_id, event_type, timestamp,
                          ev.get("zone_id"),
                          ev.get("zone_name"),
                          ev.get("zone_type"),
                          ev.get("is_revenue_zone", "Yes"),
                          dwell_ms, 0, 1.0,
                          ev.get("gender"),
                          ev.get("age"),
                          ev.get("age_bucket"),
                          json.dumps(ev)))

                elif event_type in QUEUE_TYPES:
                    wait_ms = ev.get("wait_seconds", 0) * 1000
                    conn.execute("""
                        INSERT OR IGNORE INTO events
                        (event_id, store_id, camera_id, visitor_id, event_type,
                         timestamp, zone_id, zone_name, dwell_ms, is_staff,
                         confidence, queue_depth, abandoned, gender, age,
                         age_bucket, raw_json)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (event_id, store_id,
                          ev.get("camera_id", ""),
                          visitor_id, event_type, timestamp,
                          ev.get("zone_id"),
                          ev.get("zone_name"),
                          wait_ms, 0, 1.0,
                          ev.get("queue_position_at_join", 0),
                          int(ev.get("abandoned", False)),
                          ev.get("gender"),
                          ev.get("age"),
                          ev.get("age_bucket"),
                          json.dumps(ev)))

                if conn.execute("SELECT changes()").fetchone()[0] == 0:
                    duplicate += 1
                else:
                    accepted += 1

            except Exception as e:
                rejected += 1
                errors.append({"reason": str(e), "event_type": event_type})

        conn.commit()
    finally:
        conn.close()

    ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
    log.info(json.dumps({
        "trace_id": trace_id,
        "endpoint": "/events/ingest",
        "accepted": accepted,
        "rejected": rejected,
        "duplicate": duplicate,
        "latency_ms": round(ms, 2),
        "status_code": 200
    }))
    return IngestResponse(accepted=accepted, rejected=rejected,
                          duplicate=duplicate, errors=errors)


