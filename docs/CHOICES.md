# CHOICES.md - Three Key Decisions

## Decision 1: Detection Model - MOG2 over YOLO for Edge Deployment

### Options Considered

| Option | Accuracy | CPU Speed | Download | Overhead Angle |
|--------|----------|-----------|----------|----------------|
| YOLOv8n | High | 8-12 fps | 6MB | Poor |
| YOLOv8x | Highest | 1-2 fps | 130MB | Poor |
| HOG SVM | Medium | Fast | None | Very Poor |
| MOG2 + contour | Good | 25-30 fps | None | Excellent |
| MediaPipe | Medium | Fast | 10MB | Poor |

### What AI Suggested
Claude suggested YOLOv8n as starting point citing balance of speed and
accuracy. I evaluated this seriously and ran HOG SVM on actual footage first.
HOG gave zero detections on CAM_5 billing counter due to overhead angle.

### Why I Chose MOG2 for This Deployment Context

This is a store edge deployment running on existing CCTV hardware.
The business constraint is: works on a cheap NVR box, not a GPU server.

Three reasons MOG2 wins for retail edge:

1. No GPU required. YOLOv8n on CPU gives 8fps on 1080p. MOG2 gives 25fps.
   At 15fps source footage this matters - we cannot drop frames.

2. Overhead camera angles. YOLO was trained on COCO dataset with frontal
   and 45 degree pedestrian views. Our cameras are directly overhead.
   This causes systematic false negatives in YOLO for this footage type.
   MOG2 has no such bias - it detects any moving foreground object.

3. Static background advantage. Retail stores have completely static
   backgrounds. This is exactly the use case MOG2 was designed for.
   In this scenario MOG2 accuracy matches YOLO for presence detection.

### What I Would Change at Scale
At 40 stores with dedicated GPU inference servers I would use YOLOv8n
with ByteTrack. The person bounding boxes would improve Re-ID accuracy
and handle the group entry edge case more precisely. The pipeline
architecture is identical - just swap the detector class.

### Trade-off Documented
MOG2 cannot classify person vs non-person. A swinging door or moving
display triggers detection. Mitigated by contour area filter 1500 to
130000 pixels and aspect ratio filter height divided by width above 0.25.
In practice on this footage false positive rate was under 5 percent.

## Decision 2: Event Schema - Unified with Metadata Blob

### Options Considered
Flat schema - Simple queries but breaks when new event types added
Typed events - Clean but requires different validation per type
Unified plus metadata - Chosen, stable core with extensible metadata

### What AI Suggested
Claude suggested fully flat schema. I agreed with direction but added
nested metadata object for billing-specific fields like queue_depth.

### What I Chose and Why
Unified schema with metadata blob. Core fields never change. New event
types add data to metadata without schema migrations. This is how
production event pipelines like Kafka schemas work in practice.

Key decisions I made independently:
- confidence always present never suppressed: lets downstream systems
  choose their own threshold rather than baking one into the pipeline
- dwell_ms is 0 not null for instantaneous events: AVG queries work
  without null handling, simpler analytics code
- visitor_id persists across re-entries: enables accurate funnel
  deduplication with simple DISTINCT visitor_id in SQL

### What AI Got Wrong
AI initially suggested using null for dwell_ms on ENTRY and EXIT events.
I changed this to 0 because it broke AVG(dwell_ms) queries silently.

## Decision 3: SQLite WAL over PostgreSQL

### Options Considered

| Option | Setup Time | Concurrent Reads | Write Throughput | Docker Services |
|--------|------------|------------------|------------------|-----------------|
| SQLite WAL | instant | Yes via WAL | 1000 writes/sec | 1 |
| PostgreSQL | 2 min | Yes | 10000 writes/sec | 2 |
| Redis | instant | Yes | 100000 writes/sec | 2 |

### What AI Suggested
Claude suggested PostgreSQL saying production-aware implies proper RDBMS.
I pushed back with a concrete argument about the deployment context.

### What I Chose and Why
SQLite WAL for this submission. Three concrete reasons:

1. Reviewer experience. Judge runs docker compose up on a laptop.
   PostgreSQL container takes 15-30 seconds to initialise before API
   accepts traffic. This creates a bad first impression on evaluation.

2. Event volume. 8935 events from 5 clips. SQLite handles 100 million
   rows comfortably. We are not close to any limit.

3. WAL mode solves the concurrency problem. WAL allows multiple
   simultaneous readers with one writer. API reads and dashboard
   polling work concurrently without blocking.

DATABASE_URL environment variable is the only change needed to switch
to PostgreSQL. The rest of the codebase is identical.

### Production Scaling Plan
At 40 stores sending live events the single SQLite writer becomes
the bottleneck at roughly 1000 events per second sustained.

Migration path:
Step 1 - Add Redis Streams as ingest buffer in front of writer
Step 2 - Switch DATABASE_URL to PostgreSQL
Step 3 - Add read replicas for metrics and heatmap queries
Step 4 - Partition events table by store_id and date

This is a known pattern. The current architecture makes this migration
straightforward because storage is behind a single db.py interface.

