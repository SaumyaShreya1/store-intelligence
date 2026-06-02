# CHOICES.md - Three Key Decisions

## Decision 1: Detection Model - MOG2 Background Subtraction

### Options Considered
YOLOv8 - Best accuracy but needs download, slow on CPU, poor overhead angles
HOG SVM - Built into OpenCV but tested on CAM_5 gave zero detections overhead
MOG2 plus contour - Built-in fast tunable, chose this
MediaPipe - Good pose detection but optimised for frontal views only

### What AI Suggested
Claude suggested YOLOv8n as starting point citing speed and accuracy balance.
When I raised download constraint it suggested MediaPipe.
I tested HOG first and found it failed completely on overhead footage.

### What I Chose and Why
MOG2. Retail environment has completely static background. MOG2 is
purpose-built for isolating moving foreground from static background.
Detected correctly in all 5 cameras including tricky billing counter
and entry threshold. Contour area filter 1500 to 130000 pixels and
aspect ratio filter height divided by width greater than 0.25 removed
shelf noise and display stand reflections.

### Trade-off Accepted
MOG2 does not distinguish people from other moving objects. A swinging
door would create false detections. Mitigated by contour size and
aspect ratio filters.

## Decision 2: Event Schema Design

### Options Considered
Flat schema - Simple to query but poor extensibility
Typed events - Different schema per type, complex to validate
Unified schema plus metadata blob - Chosen approach

### What AI Suggested
Claude suggested fully flat schema with optional fields per event type.
I agreed with direction but added nested metadata object to carry
billing-specific data like queue_depth and zone context like session_seq.

### What I Chose and Why
Unified schema with metadata blob. Keeps core schema stable while
allowing event types to carry extra context without schema migrations.

Key overrides from AI suggestion:
confidence always included never suppressed enables downstream filtering
dwell_ms is 0 not null for instantaneous events so AVG works without null checks
visitor_id persists across re-entries for accurate funnel deduplication

## Decision 3: SQLite with WAL over PostgreSQL

### Options Considered
FastAPI plus SQLite WAL - Zero extra services fast reads, single writer limit
FastAPI plus PostgreSQL - Production grade full SQL, needs extra Docker service
FastAPI plus Redis - Sub-millisecond reads but no persistence

### What AI Suggested
Claude suggested PostgreSQL with separate service in docker-compose saying
production-aware implies a proper RDBMS.

### What I Chose and Why
SQLite WAL. Judge runs docker compose up on a laptop. Asking them to wait
for Postgres container initialise adds friction. SQLite WAL handles
concurrent reads from API and dashboard. 8935 events total is well within
SQLite sweet spot of millions of rows.

DATABASE_URL environment variable makes upgrading to PostgreSQL a one-line change.

### Production Concern Acknowledged
At 40 stores sending live events simultaneously the SQLite single writer
becomes bottleneck. Fix is Redis Streams as ingest buffer with PostgreSQL
for storage and read replicas for metrics queries. This is documented in
README under Scaling Beyond This Submission.

