import cv2
from ultralytics import YOLO
from utils.logger import get_logger

logger = get_logger(__name__)

class PlateDetector:
    def __init__(self):
        """
        Uses YOLOv8 nano model. On first run, ultralytics auto-downloads yolov8n.pt.
        For best plate detection, swap model_path to a plate-specific YOLO model
        e.g. 'https://github.com/nicehorse06/yolov8-license-plate-detection'
        """
        logger.info("Loading YOLOv8 model for license plate detection...")
        # Uses the standard YOLOv8n as a base. For production, replace with a fine-tuned plate model.
        self.model = YOLO("yolov8n.pt")
        # Class IDs for 'car' in COCO (used to approximate plate region from car bounding box)
        self.vehicle_classes = [2, 3, 5, 7]  # car, motorcycle, bus, truck
        logger.info("YOLOv8 model loaded successfully.")

    def detect(self, frame):
        """
        Runs YOLOv8 inference on frame.
        Approximates license plate region from detected vehicle bounding boxes
        (bottom 20% of vehicle box = likely plate area).
        Returns: list of dicts with 'box' [x1, y1, x2, y2] and 'score'.
        """
        results = self.model(frame, verbose=False)[0]
        plate_boxes = []

        for box in results.boxes:
            cls_id = int(box.cls[0].item())
            conf = float(box.conf[0].item())

            if cls_id in self.vehicle_classes and conf > 0.3:
                x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
                h = y2 - y1
                w = x2 - x1
                # Approximate plate as the bottom-center 60% width, bottom 20% height of vehicle
                px1 = x1 + int(w * 0.2)
                py1 = y2 - int(h * 0.22)
                px2 = x2 - int(w * 0.2)
                py2 = y2
                plate_boxes.append({"box": [px1, py1, px2, py2], "score": conf})

        return plate_boxes
