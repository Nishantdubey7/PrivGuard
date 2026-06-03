import os
import json
import cv2
from datetime import datetime
from config.settings import FEEDBACK_DIR
from utils.logger import get_logger

logger = get_logger(__name__)

class FeedbackLogger:
    def __init__(self):
        self.images_dir = os.path.join(FEEDBACK_DIR, "images")
        self.annotations_dir = os.path.join(FEEDBACK_DIR, "annotations")
        
        os.makedirs(self.images_dir, exist_ok=True)
        os.makedirs(self.annotations_dir, exist_ok=True)
        
    def log_issue(self, frame, frame_number, box, issue_type, model_type="unknown"):
        """
        Logs an issue (missed_detection, false_positive, incorrect_redaction)
        Saves the frame and an annotation JSON.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        issue_id = f"issue_{timestamp}_{frame_number}"
        
        img_path = os.path.join(self.images_dir, f"{issue_id}.jpg")
        ann_path = os.path.join(self.annotations_dir, f"{issue_id}.json")
        
        # Save image
        cv2.imwrite(img_path, frame)
        
        # Save annotation
        annotation = {
            "issue_id": issue_id,
            "frame_number": frame_number,
            "bounding_box": box,
            "issue_type": issue_type,
            "model_type": model_type,
            "timestamp": timestamp
        }
        
        with open(ann_path, 'w') as f:
            json.dump(annotation, f, indent=4)
            
        logger.info(f"Feedback logged: {issue_type} at frame {frame_number}. Saved to {ann_path}")
