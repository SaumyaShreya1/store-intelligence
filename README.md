# Store Intelligence - Purplle Tech Challenge 2026

A complete CCTV-to-analytics pipeline for retail store intelligence.

## Quick Start

git clone https://github.com/SaumyaShreya1/store-intelligence
cd store-intelligence
pip install -r requirements.txt
python pipeline\detect.py --video clips\CAM_1.mp4 --store STORE_PURPLLE_001 --camera CAM_FLOOR_01 --layout data\store_layout.json --output data\events_CAM1.jsonl
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

## Camera Mapping

CAM_1 - CAM_FLOOR_01     - Floor   - Skincare and fragrance zone
CAM_2 - CAM_FLOOR_02     - Floor   - Makeup and cosmetics wall
CAM_3 - CAM_ENTRY_01     - Entry   - Glass door threshold entry exit
CAM_4 - CAM_STOCKROOM_01 - Back    - Stockroom staff only
CAM_5 - CAM_BILLING_01   - Billing - POS terminal and billing counter

## Run Detection on All 5 Cameras

python pipeline\detect.py --video clips\CAM_1.mp4 --store STORE_PURPLLE_001 --camera CAM_FLOOR_01 --layout data\store_layout.json --output data\events_CAM1.jsonl
python pipeline\detect.py --video clips\CAM_2.mp4 --store STORE_PURPLLE_001 --camera CAM_FLOOR_02 --layout data\store_layout.json --output data\events_CAM2.jsonl
python pipeline\detect.py --video clips\CAM_3.mp4 --store STORE_PURPLLE_001 --camera CAM_ENTRY_01 --layout data\store_layout.json --output data\events_CAM3.jsonl
python pipeline\detect.py --video clips\CAM_4.mp4 --store STORE_PURPLLE_001 --camera CAM_STOCKROOM_01 --layout data\store_layout.json --output data\events_CAM4.jsonl
python pipeline\detect.py --video clips\CAM_5.mp4 --store STORE_PURPLLE_001 --camera CAM_BILLING_01 --layout data\store_layout.json --output data\events_CAM5.jsonl

## Combine and Feed Events

Get-Content data\events_CAM1.jsonl, data\events_CAM2.jsonl, data\events_CAM3.jsonl, data\events_CAM4.jsonl, data\events_CAM5.jsonl | Set-Content data\events_all.jsonl
python scripts\feed_events.py --file data\events_all.jsonl --api http://localhost:8000

## API Endpoints

POST   /events/ingest                 - Ingest up to 500 events idempotent
GET    /stores/id/metrics             - Visitors conversion dwell queue
GET    /stores/id/funnel              - Conversion funnel with drop-off percent
GET    /stores/id/heatmap             - Zone visit heatmap normalised 0-100
GET    /stores/id/anomalies           - Active anomalies queue spike dead zone
GET    /health                        - Service health STALE_FEED warning

## Run Tests

pytest tests/ -v

Expected output: 15 passed

## Real Detection Results from Actual Footage

5 cameras processed
8935 total events detected
1916 unique visitors identified
270 entry events
371 exit events
3260 re-entry events detected
228 billing queue joins
Busiest zone: BILLING_COUNTER normalized score 100
Most dwell time: MAKEUP_WALL 1723ms average

## Scaling Beyond This Submission

At 40 live stores:
1. Replace SQLite with PostgreSQL change DATABASE_URL env var
2. Add Redis Streams ingest queue for burst writes
3. Separate read replicas for metrics queries
4. Replace MOG2 with YOLOv8 plus ByteTrack on GPU hardware

## Architecture

See docs/DESIGN.md for full architecture and AI-assisted decisions.
See docs/CHOICES.md for three key technology decisions with reasoning.

