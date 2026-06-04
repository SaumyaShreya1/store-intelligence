#!/bin/bash
# Run detection on all clips
for i in 1 2 3 4 5; do
  python pipeline/detect.py --video clips/CAM_.mp4 --store STORE_PURPLLE_001 --camera CAM_FLOOR_0 --layout data/store_layout.json --output data/events_CAM.jsonl --backend mog2
done
cat data/events_CAM*.jsonl > data/events_all.jsonl
echo 'Done. Feed events with: python scripts/feed_events.py --file data/events_all.jsonl --api http://localhost:8000'
