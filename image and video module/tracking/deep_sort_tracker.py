import numpy as np
from utils.logger import get_logger

logger = get_logger(__name__)


class KalmanBox:
    """Simple Kalman filter for a single bounding box [x1,y1,x2,y2]."""

    def __init__(self, box):
        self.box = np.array(box, dtype=float)
        self.velocity = np.zeros(4, dtype=float)
        self.age = 0
        self.missed = 0

    def predict(self):
        self.box += self.velocity
        self.age += 1
        self.missed += 1
        return self.box.tolist()

    def update(self, box):
        new_box = np.array(box, dtype=float)
        self.velocity = 0.5 * self.velocity + 0.5 * (new_box - self.box)
        self.box = new_box
        self.missed = 0


def _iou(box1, box2):
    xi1 = max(box1[0], box2[0])
    yi1 = max(box1[1], box2[1])
    xi2 = min(box1[2], box2[2])
    yi2 = min(box1[3], box2[3])
    inter = max(0, xi2 - xi1) * max(0, yi2 - yi1)
    area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
    area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
    union = area1 + area2 - inter
    return inter / union if union > 0 else 0.0


class DeepSortTracker:
    """
    Lightweight Kalman filter + IoU matching tracker.
    Approximates the DeepSORT principle (prediction + IoU-based data association).
    For production, replace with: pip install deep-sort-realtime
    """

    def __init__(self, max_missed=2, iou_threshold=0.3):
        self.trackers = {}          # track_id -> KalmanBox
        self.track_meta = {}        # track_id -> {"type": ...}
        self.next_id = 1
        self.max_missed = max_missed
        self.iou_threshold = iou_threshold
        logger.info("Initialized Kalman-IoU Tracker (DeepSORT-style).")

    def update(self, detections, frame):
        """
        Match new detections to existing tracks using IoU.
        Unmatched detections become new tracks.
        Returns list of active tracked objects.
        """
        # Predict current positions for all existing tracks
        predicted = {tid: kb.predict() for tid, kb in self.trackers.items()}

        matched_tracks = set()
        matched_dets = set()

        # Greedy IoU matching
        if self.trackers and detections:
            track_ids = list(predicted.keys())
            for di, det in enumerate(detections):
                best_iou = self.iou_threshold
                best_tid = None
                for tid in track_ids:
                    if tid in matched_tracks:
                        continue
                    iou = _iou(det["box"], predicted[tid])
                    if iou > best_iou:
                        best_iou = iou
                        best_tid = tid
                if best_tid is not None:
                    self.trackers[best_tid].update(det["box"])
                    self.track_meta[best_tid]["type"] = det.get("type", "face")
                    matched_tracks.add(best_tid)
                    matched_dets.add(di)

        # Create new tracks for unmatched detections
        for di, det in enumerate(detections):
            if di not in matched_dets:
                tid = self.next_id
                self.trackers[tid] = KalmanBox(det["box"])
                self.track_meta[tid] = {"type": det.get("type", "face")}
                self.next_id += 1
                matched_tracks.add(tid)

        # Remove tracks that have missed too many frames
        dead = [tid for tid, kb in self.trackers.items() if kb.missed > self.max_missed]
        for tid in dead:
            del self.trackers[tid]
            del self.track_meta[tid]

        return self._active_objects()

    def predict(self):
        """Return predictions for all active tracks (used on non-detection frames)."""
        for kb in self.trackers.values():
            kb.predict()
        return self._active_objects()

    def _active_objects(self):
        result = []
        for tid, kb in self.trackers.items():
            result.append({
                "track_id": tid,
                "box": [int(v) for v in kb.box],
                "type": self.track_meta[tid]["type"]
            })
        return result
