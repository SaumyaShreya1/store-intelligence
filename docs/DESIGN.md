# DESIGN.md - Store Intelligence System

## Architecture
CCTV Clips -> Detection Pipeline -> Events JSONL -> FastAPI -> SQLite -> Dashboard

## Camera Identification from visual inspection

CAM_1 - Floor skincare zone - FarmStay The Face Shop fragrance display
CAM_2 - Floor makeup zone - Loreal Lakme FacesCanada Maybelline wall
CAM_3 - Entry Exit - Glass door threshold purplle signage welcome mat
CAM_4 - Stockroom - Back office Purplle boxes inventory shelves
CAM_5 - Billing counter - POS terminal laptop haircare browsing area

All clips date 10/04/2026 start times between 20:09:45 and 20:10:27

## Detection Pipeline

Uses OpenCV MOG2 background subtractor plus custom CentroidTracker.
No external model weights required. Runs on any machine with OpenCV.

Why MOG2 over YOLO:
YOLO needs model downloads which were unavailable in deployment environment.
YOLO trained on frontal pedestrian views but our cameras are overhead angle.
MOG2 works perfectly on static retail backgrounds with no downloads needed.
Tested HOG SVM first and got zero detections on billing counter overhead angle.

Tracking uses IoU matching for slow shoppers then Euclidean distance fallback.

Re-identification uses HSV colour histograms. Above 0.78 similarity within
90 seconds means same person returning so we emit REENTRY not ENTRY.

Staff detection: track visible in first 8 seconds staying within 280x280
pixel area for 8+ seconds classified as staff is_staff true.

## Event Schema

Events follow schema in app/models.py written to data/events_all.jsonl.
confidence always included never suppressed.
is_staff flag on every event for simple WHERE is_staff=0 filtering.
visitor_id persists across re-entries REENTRY event marks re-appearance.
dwell_ms is 0 not null for instantaneous events.

## Intelligence API

FastAPI plus SQLite WAL mode. Six endpoints:
POST /events/ingest - Idempotent batch ingest dedup by event_id
GET /stores/id/metrics - Visitors conversion dwell queue abandonment
GET /stores/id/funnel - Entry to Zone to Billing to Purchase drop-off
GET /stores/id/heatmap - Zone frequency dwell normalised 0-100
GET /stores/id/anomalies - Queue spike conversion drop dead zone
GET /health - Service status STALE_FEED detection

Conversion rate: visitor in billing zone within 5 minutes before POS
transaction counts as converted. Funnel uses DISTINCT visitor_id.

## Real Detection Results

Total events: 8935
Entry events: 270
Exit events: 371
Re-entry events: 3260
Zone enter events: 4542
Billing queue joins: 228
Unique visitors: 1916
Busiest zone: BILLING_COUNTER normalized score 100

## AI-Assisted Decisions

1. MOG2 over YOLO
Claude suggested YOLO. I overrode because downloads unavailable and overhead
camera angles violate YOLO training assumptions. MOG2 detects correctly in
all 5 cameras without any downloads needed.

2. HSV histograms over deep Re-ID
Claude suggested OSNet torchreid. I chose HSV histogram similarity because
no download needed and clothing colour is dominant discriminator in retail
consistent lighting for short re-entry windows under 90 seconds.

3. SQLite over PostgreSQL
Claude suggested PostgreSQL. I chose SQLite WAL because it eliminates extra
Docker service, 8935 events well within SQLite throughput, WAL handles
concurrent reads from API and dashboard without blocking.



## Schema Update (June 2026)

After reviewing the actual sample events provided, updated schema to match:

- Entry/exit events now use `id_token`, `store_code`, `event_timestamp`  
- Added `gender_pred`, `age_pred`, `age_bucket` for demographic analytics  
- Added `group_id`, `group_size` for group entry handling  
- Added `is_face_hidden` flag for privacy-compliant detection  
- Zone events now include `zone_hotspot_x/y`, `zone_type`, `is_revenue_zone`  
- Queue events use `queue_join_ts`, `queue_served_ts`, `wait_seconds`, `abandoned`  

### AI-Assisted Decision 4: Schema Alignment

Claude helped identify the mismatch between my original schema and the actual sample events. I reviewed the sample_events.jsonl and overrode the original unified schema in favour of three typed event classes (EntryExitEvent, ZoneEvent, QueueEvent) that exactly match the provided sample. The ingestion layer now normalises all three types into a single SQLite table for query simplicity.
