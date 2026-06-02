import cv2, numpy as np, json, uuid, os, sys, argparse
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, asdict, field
from typing import Optional

class CentroidTracker:
    def __init__(self, max_disappeared=45, max_distance=160):
        self.next_id = 0
        self.tracks = {}
        self.disappeared = {}
        self.max_disappeared = max_disappeared
        self.max_distance = max_distance

    def _iou(self, a, b):
        xi1,yi1 = max(a[0],b[0]), max(a[1],b[1])
        xi2,yi2 = min(a[2],b[2]), min(a[3],b[3])
        inter = max(0,xi2-xi1)*max(0,yi2-yi1)
        ua = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - inter
        return inter/ua if ua>0 else 0

    def update(self, dets):
        if not dets:
            for tid in list(self.disappeared):
                self.disappeared[tid] += 1
                if self.disappeared[tid] > self.max_disappeared:
                    self.tracks.pop(tid, None)
                    self.disappeared.pop(tid, None)
            return {}
        if not self.tracks:
            for d in dets:
                self._reg(d)
            return {tid: self._t(d) for tid, d in self.tracks.items()}
        tids = list(self.tracks.keys())
        tboxes = [self.tracks[t] for t in tids]
        assigned_t, assigned_d = set(), set()
        pairs = sorted(
            [(self._iou(d,tb), di, ti)
             for di,d in enumerate(dets)
             for ti,tb in enumerate(tboxes)
             if self._iou(d,tb) > 0.15],
            key=lambda x: -x[0])
        for iou, di, ti in pairs:
            if di in assigned_d or ti in assigned_t:
                continue
            self.tracks[tids[ti]] = dets[di]
            self.disappeared[tids[ti]] = 0
            assigned_t.add(ti)
            assigned_d.add(di)
        for di, d in enumerate(dets):
            if di in assigned_d:
                continue
            dcx, dcy = (d[0]+d[2])//2, (d[1]+d[3])//2
            best, bti = float('inf'), None
            for ti, tb in enumerate(tboxes):
                if ti in assigned_t:
                    continue
                dist = ((dcx-(tb[0]+tb[2])//2)**2+(dcy-(tb[1]+tb[3])//2)**2)**0.5
                if dist < best:
                    best, bti = dist, ti
            if best < self.max_distance and bti is not None:
                self.tracks[tids[bti]] = dets[di]
                self.disappeared[tids[bti]] = 0
                assigned_t.add(bti)
                assigned_d.add(di)
            else:
                self._reg(dets[di])
        for ti, tid in enumerate(tids):
            if ti not in assigned_t:
                self.disappeared[tid] += 1
                if self.disappeared[tid] > self.max_disappeared:
                    self.tracks.pop(tid, None)
                    self.disappeared.pop(tid, None)
        return {tid: self._t(d) for tid, d in self.tracks.items()}

    def _reg(self, d):
        self.tracks[self.next_id] = d
        self.disappeared[self.next_id] = 0
        self.next_id += 1

    def _t(self, d):
        x1,y1,x2,y2,c = d
        return ((x1+x2)//2,(y1+y2)//2,x1,y1,x2,y2,c)


def colour_hist(frame, x1, y1, x2, y2):
    roi = frame[max(0,y1):max(0,y2), max(0,x1):max(0,x2)]
    if roi.size == 0:
        return None
    h = cv2.calcHist([cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)],
                     [0,1], None, [16,16], [0,180,0,256])
    cv2.normalize(h, h)
    return h.flatten()

def hist_sim(a, b):
    if a is None or b is None:
        return 0.0
    return float(cv2.compareHist(
        a.reshape(-1,1).astype(np.float32),
        b.reshape(-1,1).astype(np.float32),
        cv2.HISTCMP_CORREL))

def point_in_zone(cx, cy, zones):
    pt = (float(cx), float(cy))
    for name, poly in zones.items():
        if cv2.pointPolygonTest(np.array(poly, np.float32), pt, False) >= 0:
            return name
    return None

def is_staff(positions, fps, first_frame):
    if len(positions) < int(fps * 8):
        return False
    pts = np.array([(p[0], p[1]) for p in positions])
    rng = np.ptp(pts, axis=0)
    return bool(rng[0] < 280 and rng[1] < 280 and first_frame < fps * 8)

def make_ts(clip_start, frame_num, fps):
    return (clip_start + timedelta(seconds=frame_num/fps)).strftime('%Y-%m-%dT%H:%M:%SZ')


def process_clip(video_path, store_id, camera_id, clip_start,
                 zones, camera_type='floor', entry_line_y=None,
                 output_path=None, max_frames=None):

    cap = cv2.VideoCapture(video_path)
    fps   = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    w, h  = int(cap.get(3)), int(cap.get(4))
    print(f'[{camera_id}] {w}x{h} @{fps:.0f}fps | {total} frames | type={camera_type}')

    bg  = cv2.createBackgroundSubtractorMOG2(history=400, varThreshold=45, detectShadows=True)
    trk = CentroidTracker(max_disappeared=int(fps*2.5), max_distance=180)
    ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7,7))
    is_entry = camera_type == 'entry'

    visitors = {}
    exited   = []
    events   = []
    fn       = 0

    def emit(etype, v, zone=None, dwell_ms=0, conf=0.9, extra=None):
        v['seq'] += 1
        meta = {'queue_depth': None, 'sku_zone': zone, 'session_seq': v['seq']}
        if extra:
            meta.update(extra)
        events.append({
            'event_id':   str(uuid.uuid4()),
            'store_id':   store_id,
            'camera_id':  camera_id,
            'visitor_id': v['vid'],
            'event_type': etype,
            'timestamp':  make_ts(clip_start, fn, fps),
            'zone_id':    zone,
            'dwell_ms':   int(dwell_ms),
            'is_staff':   v['staff'],
            'confidence': round(float(conf), 3),
            'metadata':   meta,
        })

    while True:
        ret, frame = cap.read()
        if not ret or (max_frames and fn >= max_frames):
            break

        mask = bg.apply(frame)
        _, mask = cv2.threshold(mask, 200, 255, cv2.THRESH_BINARY)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, ker)
        mask = cv2.dilate(mask, ker, iterations=3)
        cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        dets = []
        for c in cnts:
            area = cv2.contourArea(c)
            if area < 1500 or area > 130000:
                continue
            x, y, cw, ch = cv2.boundingRect(c)
            if ch / max(cw, 1) < 0.25:
                continue
            dets.append((x, y, x+cw, y+ch, min(1.0, area/35000)))

        active = trk.update(dets)
        cur_ids = set(active.keys())

        for tid, (cx, cy, x1, y1, x2, y2, conf) in active.items():
            app = colour_hist(frame, x1, y1, x2, y2)
            if tid not in visitors:
                reid = None
                best_s = 0.0
                for ev in exited[-30:]:
                    s = hist_sim(app, ev['app'])
                    recent = (fn - ev['last_frame']) < fps * 90
                    if s > 0.78 and recent and s > best_s:
                        best_s, reid = s, ev
                if reid:
                    v = {'vid': reid['vid'], 'seq': reid['seq'],
                         'first_frame': fn, 'last_frame': fn,
                         'pos': [(cx,cy,fn)], 'zone': None,
                         'zone_enter': fn, 'dwell_emit': fn,
                         'staff': reid['staff'], 'app': app}
                    visitors[tid] = v
                    emit('REENTRY', v, conf=best_s)
                else:
                    v = {'vid': 'VIS_'+str(uuid.uuid4())[:6], 'seq': 0,
                         'first_frame': fn, 'last_frame': fn,
                         'pos': [(cx,cy,fn)], 'zone': None,
                         'zone_enter': fn, 'dwell_emit': fn,
                         'staff': False, 'app': app}
                    visitors[tid] = v
                    if is_entry:
                        emit('ENTRY', v, conf=conf)
            else:
                v = visitors[tid]
                v['last_frame'] = fn
                v['pos'].append((cx, cy, fn))
                v['app'] = app
                if fn % int(fps * 5) == 0:
                    v['staff'] = is_staff(v['pos'], fps, v['first_frame'])
                cur_zone = point_in_zone(cx, cy, zones)
                if cur_zone != v['zone']:
                    if v['zone']:
                        dw = ((fn - v['zone_enter']) / fps) * 1000
                        emit('ZONE_EXIT', v, zone=v['zone'], dwell_ms=dw, conf=conf)
                    if cur_zone:
                        emit('ZONE_ENTER', v, zone=cur_zone, conf=conf)
                        if 'BILLING' in cur_zone:
                            q = sum(1 for o in visitors.values()
                                    if o['zone'] and 'BILLING' in o['zone']
                                    and not o['staff'])
                            if q > 1:
                                emit('BILLING_QUEUE_JOIN', v, zone=cur_zone,
                                     conf=conf, extra={'queue_depth': q})
                    v['zone'] = cur_zone
                    v['zone_enter'] = fn
                    v['dwell_emit'] = fn
                elif v['zone'] and (fn - v['dwell_emit']) >= fps * 30:
                    dw = ((fn - v['dwell_emit']) / fps) * 1000
                    emit('ZONE_DWELL', v, zone=v['zone'], dwell_ms=dw, conf=conf)
                    v['dwell_emit'] = fn
                if is_entry and entry_line_y and len(v['pos']) >= 2:
                    py = v['pos'][-2][1]
                    if py < entry_line_y <= cy:
                        emit('ENTRY', v, conf=conf)
                    elif py > entry_line_y >= cy:
                        emit('EXIT', v, conf=conf)

        for tid in list(visitors.keys()):
            if tid not in cur_ids:
                v = visitors.pop(tid)
                if is_entry:
                    emit('EXIT', v, conf=0.65)
                exited.append({**v, 'last_frame': fn})

        fn += 1
        if fn % 300 == 0:
            print(f'  [{camera_id}] {fn}/{total} ({fn/total*100:.0f}%) events={len(events)} tracks={len(visitors)}')

    cap.release()
    for tid, v in visitors.items():
        if is_entry:
            emit('EXIT', v, conf=0.65)

    print(f'[{camera_id}] Done -> {len(events)} events')

    if output_path:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, 'w') as f:
            for e in events:
                f.write(json.dumps(e) + '\n')
    return events


if __name__ == '__main__':
    pa = argparse.ArgumentParser()
    pa.add_argument('--video',      required=True)
    pa.add_argument('--store',      default='STORE_PURPLLE_001')
    pa.add_argument('--camera',     default='CAM_FLOOR_01')
    pa.add_argument('--layout',     default='data/store_layout.json')
    pa.add_argument('--output',     default='data/events.jsonl')
    pa.add_argument('--max-frames', type=int, default=None)
    args = pa.parse_args()

    layout     = json.load(open(args.layout))
    store_cfg  = layout[args.store]['cameras'][args.camera]
    clip_start = datetime.strptime(
        store_cfg['clip_start'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
    zones      = store_cfg.get('zones', {})
    cam_type   = store_cfg.get('type', 'floor')
    entry_line = store_cfg.get('entry_line_y', None)

    process_clip(
        video_path=args.video,
        store_id=args.store,
        camera_id=args.camera,
        clip_start=clip_start,
        zones=zones,
        camera_type=cam_type,
        entry_line_y=entry_line,
        output_path=args.output,
        max_frames=args.max_frames,
    )
