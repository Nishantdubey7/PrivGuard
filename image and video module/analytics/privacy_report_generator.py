import json
import os
from config.settings import REPORTS_DIR
from utils.logger import get_logger

logger = get_logger(__name__)

class PrivacyReportGenerator:
    def __init__(self):
        self.stats = {
            "video_duration_sec": 0,
            "faces_redacted": 0,
            "plates_redacted": 0,
            "pii_detected": {},
            "privacy_risk_score": 0,
            "max_score": 50
        }

    def generate_report(self, filename="privacy_report.json"):
        filepath = os.path.join(REPORTS_DIR, filename)
        logger.info(f"Generating Privacy Report at {filepath}")
        
        # Calculate total risk score based on aggregated stats
        score = 0
        score += self.stats["faces_redacted"] * 2
        score += self.stats["plates_redacted"] * 3
        
        for k, v in self.stats["pii_detected"].items():
            if "phone" in k.lower(): score += v * 4
            elif "address" in k.lower(): score += v * 5
            elif "name" in k.lower(): score += v * 4
            else: score += v * 3
            
        self.stats["privacy_risk_score"] = min(score, self.stats["max_score"])
        
        with open(filepath, 'w') as f:
            json.dump(self.stats, f, indent=4)
            
        logger.info(f"Privacy Risk Score: {self.stats['privacy_risk_score']} / {self.stats['max_score']}")
        return filepath
