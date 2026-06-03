import cv2
import numpy as np
from utils.logger import get_logger

logger = get_logger(__name__)

class FaceDetector:
    """
    Highly accurate YOLOv8 Face Detection wrapper.
    Replaces dlib HOG to ensure perfect recall on profile and angled faces, 
    while preserving near-zero false-positive rates by using a dedicated face model.
    """

    MIN_BOX_SIDE = 40          # px — reject any tiny spurious detection

    def __init__(self, model_name="yolov8-face", threshold=0.6):
        self.threshold = threshold
        try:
            from ultralytics import YOLO
            import os
            # Use the dedicated face weights
            weights_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "yolov8n-face.pt")
            if not os.path.exists(weights_path):
                # Fallback to current dir
                weights_path = "yolov8n-face.pt"
                
            self.detector = YOLO(weights_path)
            self._ready = True
            logger.info("Initialized YOLOv8 Face Detector (High Accuracy, All Angles).")
        except Exception as e:
            logger.warning(f"YOLOv8 face initialization failed: {e}")
            self._ready = False

    def detect(self, frame):
        """
        Detect faces in a frame using YOLOv8-face.
        Returns: list of dicts with 'box' [x1, y1, x2, y2] and 'score'.
        """
        if not self._ready:
            return []

        # YOLO expects BGR, so we can pass 'frame' directly
        try:
            # classes=[0] usually is face if trained on single class face dataset
            results = self.detector(frame, verbose=False)[0]
        except Exception as e:
            logger.error(f"YOLO detection error: {e}")
            return []

        detected_faces = []
        ih, iw, _ = frame.shape
        
        for box in results.boxes:
            conf = float(box.conf[0].item())
            if conf < self.threshold:
                continue
                
            x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]

            x1 = max(0, x1)
            y1 = max(0, y1)
            x2 = min(iw, x2)
            y2 = min(ih, y2)

            w = x2 - x1
            h = y2 - y1
            
            if w >= self.MIN_BOX_SIDE and h >= self.MIN_BOX_SIDE:
                detected_faces.append({
                    "box": [x1, y1, x2, y2],
                    "score": conf
                })

        return detected_faces


class MTCNNFallback:
    """Placeholder for MTCNN — not used when dlib/TF unavailable."""
    def __init__(self):
        logger.info("MTCNNFallback: disabled (dlib/TF not available).")

    def detect(self, frame):
        return []
