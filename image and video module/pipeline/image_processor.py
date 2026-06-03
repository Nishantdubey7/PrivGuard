from models.plate_detector import PlateDetector
from models.text_detector import TextDetector
from models.ocr_engine import OCREngine
from ensemble.ensemble_detector import EnsembleDetector
from recognition.face_recognition import FaceRecognizer
from policy.privacy_policy_engine import PrivacyPolicyEngine
from redaction.blackbox import apply_blackbox

class ImageProcessor:
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
            
    def process_image(self, image):
        """Processes a single image, identifying elements and applying redaction"""
        detections = []
        
        # 1. Detection Phase
        if getattr(self, "face_detector", None):
            faces = self.face_detector.detect(image)
            for f in faces: f["type"] = "face"
            detections.extend(faces)
            
        if getattr(self, "plate_detector", None):
            plates = self.plate_detector.detect(image)
            for p in plates: p["type"] = "plate"
            detections.extend(plates)
            
        # 2. PII Text Detection
        if getattr(self, "text_detector", None):
            text_regions = self.text_detector.detect(image)
            pii_regions = self.ocr_engine.analyze_regions(image, text_regions)
            for text in pii_regions:
                # Text redaction box
                detections.append({"box": text["box"], "type": text["entity_type"], "text": text["text"]})
                
        # 3. Redaction Application
        stats_to_report = []
        for item in detections:
            box = item["box"]
            item_type = item["type"]
            
            # Policy Application
            redact = False
            
            if item_type == "face" and self.policy.should_redact_face():
                is_auth = False
                    
                if not is_auth and self.recognizer:
                    is_auth = self.recognizer.is_authorized(image, box)
                    
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
                image = apply_blackbox(image, box)
                    
        return image, stats_to_report
