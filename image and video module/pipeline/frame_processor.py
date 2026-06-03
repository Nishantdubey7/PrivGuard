from config.settings import TRACKING_INTERVAL
from models.plate_detector import PlateDetector
from models.text_detector import TextDetector
from models.ocr_engine import OCREngine
from ensemble.ensemble_detector import EnsembleDetector
from recognition.face_recognition import FaceRecognizer
from tracking.deep_sort_tracker import DeepSortTracker
from policy.privacy_policy_engine import PrivacyPolicyEngine
from redaction.blackbox import apply_blackbox

class FrameProcessor:
    def __init__(self, mode, identity_image_path=None):
        self.policy = PrivacyPolicyEngine(mode)
        
        # Initialize Models
        if self.policy.should_redact_face():
            self.face_detector = EnsembleDetector()
        
        if self.policy.should_redact_plate():
            self.plate_detector = PlateDetector()
            
        if self.policy.should_redact_pii():
            self.text_detector = TextDetector()
            self.ocr_engine = OCREngine()
            
        # Recognition
        self.recognizer = None
        if self.policy.policy.get("keep_authorized") and identity_image_path:
            self.recognizer = FaceRecognizer()
            self.recognizer.load_authorized_identity(identity_image_path)
            
        # Tracking
        self.tracker = DeepSortTracker()
        
        # Identity Caching (Track_ID -> Boolean)
        self.auth_cache = {}
        
    def process_frame(self, frame, frame_number):
        """Processes a single frame, identifying elements and applying redaction"""
        detections = []
        is_detection_frame = (frame_number % TRACKING_INTERVAL == 0)
        
        # 1. Detection Phase (or rely on tracking)
        if is_detection_frame:
            # Detect everything required by policy
            if getattr(self, "face_detector", None):
                faces = self.face_detector.detect(frame)
                for f in faces: f["type"] = "face"
                detections.extend(faces)
                
            if getattr(self, "plate_detector", None):
                plates = self.plate_detector.detect(frame)
                for p in plates: p["type"] = "plate"
                detections.extend(plates)
        else:
            # Predict from tracker
            pass  # For simplicity, we assume tracking returns boxes without running heavy models
            
        # 2. Tracking update
        if is_detection_frame:
            tracked_objects = self.tracker.update(detections, frame)
        else:
            tracked_objects = self.tracker.predict()
            
        # Map tracker outputs back to format with type if needed
        final_boxes = []
        for det in tracked_objects:
            final_boxes.append({
                "box": det["box"], 
                "type": det.get("type", "face"),
                "track_id": det.get("track_id", None)
            })

        # 3. PII Text Detection (Usually don't track text, detect per frame or interval)
        if getattr(self, "text_detector", None) and is_detection_frame:
            text_regions = self.text_detector.detect(frame)
            pii_regions = self.ocr_engine.analyze_regions(frame, text_regions)
            for text in pii_regions:
                # Text redaction box
                final_boxes.append({"box": text["box"], "type": text["entity_type"], "text": text["text"]})
                
        # 4. Redaction Application
        stats_to_report = []
        for item in final_boxes:
            box = item["box"]
            item_type = item["type"]
            
            # Policy Application
            redact = False
            
            if item_type == "face" and self.policy.should_redact_face():
                # Check identity if authorized
                track_id = item.get("track_id")
                is_auth = False
                
                # If we already authorized this tracked face in a previous frame, keep it authorized
                if track_id is not None and self.auth_cache.get(track_id, False):
                    is_auth = True
                    
                if not is_auth and self.recognizer:
                    is_auth = self.recognizer.is_authorized(frame, box)
                    if is_auth and track_id is not None:
                        # Once authorized, permanently cache it for this track
                        self.auth_cache[track_id] = True
                    
                if not is_auth:
                    redact = True
                    stats_to_report.append({"type": "face"})
                    
            elif item_type == "plate" and self.policy.should_redact_plate():
                redact = True
                stats_to_report.append({"type": "plate"})
                
            elif item_type not in ["face", "plate"] and self.policy.should_redact_pii():
                # It's some kind of PII text
                redact = True
                stats_to_report.append({"type": str(item_type)})
                
            # Apply drawing
            if redact:
                frame = apply_blackbox(frame, box)
                    
        return frame, stats_to_report
