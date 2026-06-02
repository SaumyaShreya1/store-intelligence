from pydantic import BaseModel, Field
from typing import Optional, List


class EventMetadata(BaseModel):
    queue_depth: Optional[int] = None
    sku_zone: Optional[str] = None
    session_seq: int = 0


class Event(BaseModel):
    event_id: str
    store_id: str
    camera_id: str
    visitor_id: str
    event_type: str
    timestamp: str
    zone_id: Optional[str] = None
    dwell_ms: int = 0
    is_staff: bool = False
    confidence: float = 0.9
    metadata: EventMetadata = Field(default_factory=EventMetadata)


class IngestRequest(BaseModel):
    events: List[Event]


class IngestResponse(BaseModel):
    accepted: int
    rejected: int
    duplicate: int
    errors: List[dict] = []


class ZoneMetric(BaseModel):
    zone_id: str
    visit_count: int
    avg_dwell_ms: float
    normalized_score: float = 0.0


class StoreMetrics(BaseModel):
    store_id: str
    unique_visitors: int
    conversion_rate: float
    avg_dwell_ms: float
    queue_depth: int
    abandonment_rate: float
    zones: List[ZoneMetric]
    window_minutes: int
    data_confidence: str = 'HIGH'


class FunnelStage(BaseModel):
    stage: str
    count: int
    drop_off_pct: float


class StoreFunnel(BaseModel):
    store_id: str
    stages: List[FunnelStage]


class HeatmapZone(BaseModel):
    zone_id: str
    visit_count: int
    avg_dwell_ms: float
    normalized_score: float
    data_confidence: str = 'HIGH'


class StoreHeatmap(BaseModel):
    store_id: str
    zones: List[HeatmapZone]


class Anomaly(BaseModel):
    anomaly_id: str
    anomaly_type: str
    severity: str
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
