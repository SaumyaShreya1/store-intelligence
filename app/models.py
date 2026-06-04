from pydantic import BaseModel, Field
from typing import Optional, List

# --- Entry / Exit Events (Camera 1 - Entry camera) ---
class EntryExitEvent(BaseModel):
    event_type: str                          # "entry" or "exit"
    id_token: str                            # unique visitor token e.g. "ID_60001"
    store_code: str                          # e.g. "store_1076"
    camera_id: str                           # e.g. "cam1"
    event_timestamp: str                     # ISO-8601
    is_staff: bool = False
    gender_pred: Optional[str] = None        # "M" or "F"
    age_pred: Optional[int] = None           # e.g. 28
    age_bucket: Optional[str] = None         # e.g. "25-34"
    is_face_hidden: bool = False
    group_id: Optional[str] = None           # e.g. "G_10"
    group_size: Optional[int] = None         # e.g. 2

# --- Zone Events (Floor cameras) ---
class ZoneEvent(BaseModel):
    event_type: str                          # "zone_entered" or "zone_exited"
    track_id: int                            # tracker ID
    store_id: str                            # e.g. "ST1076"
    camera_id: str
    zone_id: str                             # e.g. "PURPLLE_MUM_1076_Z01"
    zone_name: str                           # e.g. "Left Shelf"
    zone_type: str                           # "SHELF", "DISPLAY", "BILLING"
    is_revenue_zone: str                     # "Yes" or "No"
    event_time: str                          # ISO-8601
    zone_hotspot_x: Optional[float] = None
    zone_hotspot_y: Optional[float] = None
    gender: Optional[str] = None
    age: Optional[int] = None
    age_bucket: Optional[str] = None

# --- Queue Events (Billing camera) ---
class QueueEvent(BaseModel):
    queue_event_id: str                      # UUID
    event_type: str                          # "queue_completed" or "queue_abandoned"
    track_id: int
    store_id: str
    camera_id: str
    zone_id: str
    zone_name: str
    zone_type: str = "BILLING"
    is_revenue_zone: str = "Yes"
    queue_join_ts: str
    queue_served_ts: Optional[str] = None
    queue_exit_ts: str
    wait_seconds: int
    queue_position_at_join: int
    abandoned: bool
    zone_hotspot_x: Optional[float] = None
    zone_hotspot_y: Optional[float] = None
    gender: Optional[str] = None
    age: Optional[int] = None
    age_bucket: Optional[str] = None

# --- Generic ingest (accepts all event types) ---
class IngestRequest(BaseModel):
    events: List[dict]

class IngestResponse(BaseModel):
    accepted: int
    rejected: int
    duplicate: int
    errors: List[dict] = []

# --- API Response Models ---
class ZoneMetric(BaseModel):
    zone_id: str
    zone_name: str = ""
    visit_count: int
    avg_dwell_ms: float
    normalized_score: float = 0.0
    is_revenue_zone: bool = True

class StoreMetrics(BaseModel):
    store_id: str
    unique_visitors: int
    conversion_rate: float
    avg_dwell_ms: float
    queue_depth: int
    abandonment_rate: float
    zones: List[ZoneMetric]
    window_minutes: int
    data_confidence: str = "HIGH"
    gender_breakdown: dict = Field(default_factory=dict)
    age_breakdown: dict = Field(default_factory=dict)

class FunnelStage(BaseModel):
    stage: str
    count: int
    drop_off_pct: float

class StoreFunnel(BaseModel):
    store_id: str
    stages: List[FunnelStage]

class HeatmapZone(BaseModel):
    zone_id: str
    zone_name: str = ""
    visit_count: int
    avg_dwell_ms: float
    normalized_score: float
    data_confidence: str = "HIGH"

class StoreHeatmap(BaseModel):
    store_id: str
    zones: List[HeatmapZone]

class Anomaly(BaseModel):
    anomaly_id: str
    anomaly_type: str
    severity: str                            # "INFO", "WARN", "CRITICAL"
    description: str
    suggested_action: str
    detected_at: str
    store_id: str
    zone_id: Optional[str] = None

class HealthStore(BaseModel):
    store_id: str
    last_event_at: Optional[str]
    status: str
    lag_seconds: Optional[float] = None

class HealthResponse(BaseModel):
    status: str
    uptime_seconds: float
    stores: List[HealthStore]
    checked_at: str
