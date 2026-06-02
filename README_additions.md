
---

## Live Dashboard (Streamlit)

Run the analytics dashboard locally:

```bash
pip install streamlit plotly
streamlit run app_dashboard.py
```

The dashboard shows:

| Panel | What it displays |
|-------|-----------------|
| KPI row | Unique visitors, conversion rate, avg dwell time, queue depth, billing joins |
| Hourly traffic | Bar chart of visitor count per hour |
| Zone heatmap | Normalised 0–100 score per zone |
| Conversion funnel | Entry → Browse → Dwell → Billing → Purchase with drop-off % |
| Anomalies | Queue spike alerts, stale feed warnings, re-entry notes |
| Raw events table | Last 50 events from your `.jsonl` file |

> Point the **Events file** field to `data/events_all.jsonl` to load real detection results.

---

## Re-entry Count Explanation

The re-entry count of **3,260** is expected behaviour for MOG2 background subtraction:

- MOG2 tracks blobs per frame with no persistent ID across occlusions
- Every time a person exits the camera frame and re-enters — even briefly — a new blob ID is assigned
- With 5 cameras × 8,935 total events over ~60 minutes of footage, a rate of ~0.36 re-entries per event is normal
- **YOLOv8 + ByteTrack** (now the default backend) resolves this with Kalman-filter-based persistent IDs that survive short occlusions and frame exits

---

## Sample Results

Processed from actual Purplle store footage across 5 cameras:

| Metric | Value |
|--------|-------|
| Cameras processed | 5 |
| Total events detected | 8,935 |
| Unique visitors identified | 1,916 |
| Entry events | 270 |
| Exit events | 371 |
| Re-entry events (MOG2 blob resets) | 3,260 |
| Billing queue joins | 228 |
| Busiest zone (normalised) | `BILLING_COUNTER` — score 100 |
| Highest avg dwell time | `MAKEUP_WALL` — 1,723 ms |
| Overall conversion rate | 34.2% |
