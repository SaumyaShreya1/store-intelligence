"""
pipeline/detect.py

Detection pipeline supporting two backends:
  --backend mog2       : Background subtraction (MOG2) — CPU only, no weights needed
  --backend yolo       : YOLOv8n + ByteTrack — GPU-accelerated when available

Usage
-----
python pipeline/detect.py \
    --video clips/CAM_1.mp4 \
    --store STORE_PURPLLE_001 \
    --camera CAM_FLOOR_01 \
    --layout data/store_layout.json \
    --output data/events_CAM1.jsonl \
    --backend yolo          # optional, default=yolo; use mog2 for CPU-only envs
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import cv2
import numpy as np


# ---------------------------------------------------------------------------
# Zone helpers
# ---------------------------------------------------------------------------

def load_layout(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def point_in_zone(cx: int, cy: int, zone: dict) -> bool:
    """Return True if (cx, cy) falls inside the zone polygon."""
    pts = np.array(zone["polygon"], dtype=np.int32)
    return cv2.pointPolygonTest(pts, (float(cx), float(cy)), False) >= 0


def zone_for_centroid(cx: int, cy: int, zones: list[dict]) -> str | None:
    for z in zones:
        if point_in_zone(cx, cy, z):
            return z["id"]
    return None


# ---------------------------------------------------------------------------
# MOG2 backend (original, CPU-only)
# ---------------------------------------------------------------------------

class MOG2Detector:
    """
    Background-subtraction detector using OpenCV MOG2.
    Produces one bounding box per connected component above a size threshold.
    Each component is treated as a separate 'track' keyed by a simple frame
    index so downstream code has a stable track_id-like value.
    """

    def __init__(self, min_area: int = 500):
        self.bg = cv2.createBackgroundSubtractorMOG2(
            history=500, varThreshold=50, detectShadows=True
        )
        self.min_area = min_area

    def process(self, frame: np.ndarray) -> list[dict]:
        """Return list of {track_id, cx, cy, bbox} dicts for the frame."""
        mask = self.bg.apply(frame)
        # Remove shadows (grey pixels = 127)
        _, mask = cv2.threshold(mask, 200, 255, cv2.THRESH_BINARY)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_DILATE, kernel)

        n_labels, _, stats, centroids = cv2.connectedComponentsWithStats(mask)
        detections = []
        for i in range(1, n_labels):  # skip background label 0
            area = stats[i, cv2.CC_STAT_AREA]
            if area < self.min_area:
                continue
            cx, cy = int(centroids[i][0]), int(centroids[i][1])
            x, y = stats[i, cv2.CC_STAT_LEFT], stats[i, cv2.CC_STAT_TOP]
            w, h = stats[i, cv2.CC_STAT_WIDTH], stats[i, cv2.CC_STAT_HEIGHT]
            detections.append(
                {"track_id": i, "cx": cx, "cy": cy, "bbox": [x, y, x + w, y + h]}
            )
        return detections


# ---------------------------------------------------------------------------
# YOLOv8 + ByteTrack backend
# ---------------------------------------------------------------------------

class YOLOByteTrackDetector:
    """
    Person detector using YOLOv8n + ByteTrack multi-object tracker.
    Requires: ultralytics>=8.2 and supervision>=0.21
    Falls back to MOG2 with a warning if either package is missing.
    """

    PERSON_CLASS = 0  # COCO class index for 'person'

    def __init__(self, model_name: str = "yolov8n.pt", conf: float = 0.35):
        try:
            from ultralytics import YOLO
            import supervision as sv
        except ImportError as e:
            raise ImportError(
                "YOLOv8 backend requires: pip install ultralytics supervision lap\n"
                f"Original error: {e}"
            ) from e

        self.model = YOLO(model_name)
        self.tracker = sv.ByteTracker(
            track_activation_threshold=0.25,
            lost_track_buffer=30,
            minimum_matching_threshold=0.8,
            frame_rate=25,
        )
        self.conf = conf
        self._sv = sv  # keep reference

    def process(self, frame: np.ndarray) -> list[dict]:
        results = self.model(
            frame,
            classes=[self.PERSON_CLASS],
            conf=self.conf,
            verbose=False,
        )[0]

        # Convert YOLO results → supervision Detections
        detections = self._sv.Detections.from_ultralytics(results)

        # Run ByteTrack
        tracked = self.tracker.update_with_detections(detections)

        output = []
        for i, (xyxy, track_id) in enumerate(
            zip(tracked.xyxy, tracked.tracker_id)
        ):
            x1, y1, x2, y2 = map(int, xyxy)
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
            output.append(
                {
                    "track_id": int(track_id),
                    "cx": cx,
                    "cy": cy,
                    "bbox": [x1, y1, x2, y2],
                }
            )
        return output


# ---------------------------------------------------------------------------
# Event builder
# ---------------------------------------------------------------------------

_DWELL_THRESHOLD_S = 3.0   # seconds in a zone before emitting a dwell event
_ENTRY_ZONE_IDS   = {"ENTRY_DOOR", "GLASS_THRESHOLD"}  # camera-specific entry zones


class TrackState:
    __slots__ = ("zone", "zone_since", "emitted_dwell")

    def __init__(self):
        self.zone: str | None = None
        self.zone_since: float = 0.0
        self.emitted_dwell: bool = False


def build_event(
    event_type: str,
    track_id: int,
    zone: str | None,
    store_id: str,
    camera_id: str,
    ts: float,
    extra: dict | None = None,
) -> dict[str, Any]:
    ev = {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "track_id": track_id,
        "zone": zone,
        "store_id": store_id,
        "camera_id": camera_id,
        "timestamp": round(ts, 3),
    }
    if extra:
        ev.update(extra)
    return ev


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run(
    video_path: str,
    store_id: str,
    camera_id: str,
    layout_path: str,
    output_path: str,
    backend: str = "yolo",
    yolo_model: str = "yolov8n.pt",
    conf: float = 0.35,
):
    layout = load_layout(layout_path)
    zones = layout.get("zones", [])

    # Build detector
    if backend == "mog2":
        detector = MOG2Detector()
        print(f"[detect] Backend: MOG2 (CPU)")
    else:
        try:
            detector = YOLOByteTrackDetector(model_name=yolo_model, conf=conf)
            print(f"[detect] Backend: YOLOv8 + ByteTrack  model={yolo_model}")
        except ImportError as exc:
            print(f"[detect] WARNING: {exc}")
            print("[detect] Falling back to MOG2 backend.")
            detector = MOG2Detector()

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        sys.exit(f"[detect] Cannot open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"[detect] Video: {video_path}  fps={fps:.1f}  frames={total_frames}")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    track_states: dict[int, TrackState] = {}
    seen_tracks: set[int] = set()
    event_count = 0
    wall_start = time.time()

    with output_path.open("w") as out_f:

        def emit(ev: dict):
            nonlocal event_count
            out_f.write(json.dumps(ev) + "\n")
            event_count += 1

        frame_idx = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            ts = frame_idx / fps
            detections = detector.process(frame)

            for det in detections:
                tid = det["track_id"]
                cx, cy = det["cx"], det["cy"]
                current_zone = zone_for_centroid(cx, cy, zones)

                # --- First time we see this track ---
                if tid not in seen_tracks:
                    seen_tracks.add(tid)
                    track_states[tid] = TrackState()

                    if current_zone in _ENTRY_ZONE_IDS:
                        emit(build_event("entry", tid, current_zone, store_id, camera_id, ts))
                    else:
                        emit(build_event("appear", tid, current_zone, store_id, camera_id, ts))

                state = track_states[tid]

                # --- Zone transition ---
                if current_zone != state.zone:
                    if state.zone is not None:
                        emit(
                            build_event(
                                "zone_exit",
                                tid,
                                state.zone,
                                store_id,
                                camera_id,
                                ts,
                                {"dwell_ms": round((ts - state.zone_since) * 1000)},
                            )
                        )
                    if current_zone is not None:
                        emit(build_event("zone_enter", tid, current_zone, store_id, camera_id, ts))

                    state.zone = current_zone
                    state.zone_since = ts
                    state.emitted_dwell = False

                # --- Dwell event ---
                if (
                    current_zone is not None
                    and not state.emitted_dwell
                    and (ts - state.zone_since) >= _DWELL_THRESHOLD_S
                ):
                    emit(
                        build_event(
                            "dwell",
                            tid,
                            current_zone,
                            store_id,
                            camera_id,
                            ts,
                            {"dwell_ms": round((ts - state.zone_since) * 1000)},
                        )
                    )
                    state.emitted_dwell = True

            frame_idx += 1

        # --- Emit exit / disappear for all tracks still active ---
        for tid, state in track_states.items():
            ts = frame_idx / fps
            ev_type = "exit" if state.zone in _ENTRY_ZONE_IDS else "disappear"
            emit(build_event(ev_type, tid, state.zone, store_id, camera_id, ts))

    cap.release()
    elapsed = time.time() - wall_start
    print(
        f"[detect] Done — {event_count} events · {len(seen_tracks)} tracks · "
        f"{elapsed:.1f}s  ({frame_idx / elapsed:.0f} fps processed)"
    )
    print(f"[detect] Output → {output_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Store-Intelligence detection pipeline")
    p.add_argument("--video",   required=True,  help="Path to video file")
    p.add_argument("--store",   required=True,  help="Store ID")
    p.add_argument("--camera",  required=True,  help="Camera ID")
    p.add_argument("--layout",  required=True,  help="Path to store_layout.json")
    p.add_argument("--output",  required=True,  help="Output .jsonl path")
    p.add_argument(
        "--backend",
        default="yolo",
        choices=["yolo", "mog2"],
        help="Detection backend (default: yolo)",
    )
    p.add_argument("--model",   default="yolov8n.pt", help="YOLOv8 model weights")
    p.add_argument("--conf",    default=0.35, type=float, help="YOLO confidence threshold")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(
        video_path=args.video,
        store_id=args.store,
        camera_id=args.camera,
        layout_path=args.layout,
        output_path=args.output,
        backend=args.backend,
        yolo_model=args.model,
        conf=args.conf,
    )
