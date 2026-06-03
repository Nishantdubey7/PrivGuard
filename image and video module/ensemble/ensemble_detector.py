from config.settings import ENSEMBLE_MIN_VOTES, CONFIDENCE_THRESHOLD_FACE
from models.face_detector import FaceDetector, MTCNNFallback
from utils.logger import get_logger

logger = get_logger(__name__)

def compute_iou(box1, box2):
    """Compute Intersection over Union between two boxes."""
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])

    inter_area = max(0, x2 - x1) * max(0, y2 - y1)
    box1_area = (box1[2] - box1[0]) * (box1[3] - box1[1])
    box2_area = (box2[2] - box2[0]) * (box2[3] - box2[1])

    if float(box1_area + box2_area - inter_area) == 0:
        return 0.0
    return inter_area / float(box1_area + box2_area - inter_area)

class EnsembleDetector:
    def __init__(self):
        logger.info("Initializing Ensemble Face Detector")
        self.detectors = [
            FaceDetector(model_name="retinaface", threshold=CONFIDENCE_THRESHOLD_FACE),
            MTCNNFallback()
        ]

    def detect(self, frame):
        """
        Runs multiple face detectors and aggregates the results.
        Requires at least ENSEMBLE_MIN_VOTES to confirm a detection.
        """
        all_detections = []
        for det in self.detectors:
            all_detections.append(det.detect(frame))

        # Flatten list of lists and vote
        # Naive implementation: group by IOU > 0.5
        confirmed_boxes = []
        flat_detects = [d for sublist in all_detections for d in sublist]

        if not flat_detects:
            return []

        # Find groups of overlapping boxes
        used = set()
        for i, det1 in enumerate(flat_detects):
            if i in used:
                continue
            votes = 1
            group_boxes = [det1["box"]]
            used.add(i)

            for j, det2 in enumerate(flat_detects):
                if j in used:
                    continue
                if compute_iou(det1["box"], det2["box"]) > 0.5:
                    votes += 1
                    group_boxes.append(det2["box"])
                    used.add(j)

            if votes >= ENSEMBLE_MIN_VOTES:
                # Average the box coordinates of the group
                avg_box = [sum(x)/len(x) for x in zip(*group_boxes)]
                avg_box = [int(v) for v in avg_box]
                confirmed_boxes.append({"box": avg_box, "confidence_votes": votes})

        return confirmed_boxes
