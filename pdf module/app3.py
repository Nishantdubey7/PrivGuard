# ==================== STANDARD LIBRARIES ====================
import os
import re
import json
import time
import shutil
import hashlib
import argparse
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
from collections import defaultdict
from PIL import ImageFont


# ==================== NUMERICAL ====================
import numpy as np

# ==================== MACHINE LEARNING ====================
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
import joblib
import torch
from transformers import pipeline

# ==================== OCR ====================
import cv2
import pytesseract
from pytesseract import Output
from pdf2image import convert_from_path

# ==================== IMAGE PROCESSING ====================
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter

# ==================== TEXT MATCHING ====================
from fuzzywuzzy import fuzz

 
# ==================== CONFIGURATION ====================
BASE = Path(".").resolve()
OUTPUTS_DIR = BASE / "outputs"
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

# Self-training configuration
TRAINING_DIR = BASE / "training_data"
FEEDBACK_DIR = TRAINING_DIR / "feedback"
MODEL_CACHE_DIR = BASE / "model_cache"
PRIVACY_CONFIG = {
    "auto_delete_training_data": True,
    "retention_days": 7,
    "anonymize_feedback": True,
    "use_differential_privacy": True,
    "privacy_epsilon": 1.0,
}

for dir_path in [TRAINING_DIR, FEEDBACK_DIR, MODEL_CACHE_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)

# OCR Configuration
PDF_DPI = 300
OCR_PSM = 6
OCR_OEM = 3
OCR_ENGINES = ["tesseract", "easyocr"]
 
# NER Configuration
AI_MODELS = [
    "dslim/bert-base-NER",
    # "xlm-roberta-large-finetuned-conll03-english",
    "Davlan/distilbert-base-multilingual-cased-ner-hrl",
    # "d4data/biomedical-ner-all"
]
 
# Redaction Configuration
PAD_PIXELS = 5
MIN_BOX_WH = 8
MAX_BOX_WIDTH = 800
MAX_BOX_HEIGHT = 200
MAX_BOX_AREA = 50000
 
# Global state
_NER_PIPELINES = []
_NER_LOADED = False
_EASYOCR_READER = None
_CONFIDENCE_CALIBRATOR = None
_PRIVACY_MANAGER = None
_TRAINING_SYSTEM = None

# ==================== PATTERNS ====================
ID_PATTERNS = [
    # Indian IDs
    (re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"), "B-DOC", "PAN", 100),
    (re.compile(r"\b\d{4}\s*\d{4}\s*\d{4}\b"), "B-DOC", "AADHAAR", 95),
    (re.compile(r"\b\d{12}\b"), "B-DOC", "AADHAAR", 90),
    (re.compile(r"\b[A-Z]\d{7}\b"), "B-DOC", "PASSPORT", 85),
    (re.compile(r"\b[A-Z]{2}[\s-]?\d{2}[\s-]?\d{11}\b"), "B-DOC", "DL", 85),
    
    # Contact
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"), "B-EMAIL", "EMAIL", 90),
    (re.compile(r"\b\+91[\s-]?[6-9]\d{9}\b"), "B-PHONE", "PHONE", 85),
    (re.compile(r"\b[6-9]\d{9}\b"), "B-PHONE", "PHONE", 75),
    
    # Dates
    (re.compile(r"\b\d{2}[/\-\.]\d{2}[/\-\.]\d{4}\b"), "B-DATE", "DOB", 85),
    (re.compile(r"\b\d{4}[/\-\.]\d{2}[/\-\.]\d{2}\b"), "B-DATE", "DOB", 80),
    
    # Financial
    (re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"), "B-FINANCIAL", "CARD", 85),
    
    # Location
    (re.compile(r"\b[1-9]\d{5}\b"), "B-LOC", "PINCODE", 40),
    (re.compile(r"\b\d{1,4}\s+[A-Za-z]+\s+(Street|St|Road|Rd|Lane|Ln|Nagar|Colony)\b", re.IGNORECASE),"B-LOC", "ADDRESS", 85),
    
    (re.compile(r"\b\d{10,15}\b"), "B-SENSITIVE", "GENERIC_ID", 70),
   
]

HEALTH_PATTERNS = [
    (re.compile(r"\bMRN[:\s]*\d+\b", re.IGNORECASE), "B-HEALTH", "MRN", 95),
    (re.compile(r"\bPatient\s*ID[:\s]*\w+\b", re.IGNORECASE), "B-HEALTH", "PATIENT_ID", 95),
    (re.compile(r"\bBlood\s*Group[:\s]*[ABO]{1,2}[+-]\b", re.IGNORECASE), "B-HEALTH", "BLOOD_GROUP", 80),
    (re.compile(r"\b(HIV|AIDS|Cancer|Diabetes|Tuberculosis|TB)\b", re.IGNORECASE), "B-HEALTH", "DIAGNOSIS", 85),
    (re.compile(r"\bPrescription\s*No[:\s]*\w+\b", re.IGNORECASE), "B-HEALTH", "PRESCRIPTION", 90),
    (re.compile(r"\bInsurance\s*ID[:\s]*\w+\b", re.IGNORECASE), "B-HEALTH", "INSURANCE_ID", 90),
]

PASSPORT_PATTERN = re.compile(r"\b[A-Z][0-9]{7}\b")
MRZ_PATTERN = re.compile(r"[A-Z0-9<]{30,}")
PIN_PATTERN = re.compile(r"\b[1-9]\d{5}\b")
 
SENSITIVE_FIELD_PATTERNS = [
    (re.compile(r"^(name|नाम)$", re.IGNORECASE), "B-PER", "NAME_FIELD", 95),
    (re.compile(r"(father'?s?\s+name|पिता\s*का\s*नाम)", re.IGNORECASE), "B-PER", "FATHER_NAME", 95),
    (re.compile(r"(mother'?s?\s+name|माता\s*का\s*नाम)", re.IGNORECASE), "B-PER", "MOTHER_NAME", 95),
    (re.compile(r"(date\s+of\s+birth|dob|जन्म\s*तिथि)", re.IGNORECASE), "B-DATE", "DOB_FIELD", 90),
    (re.compile(r"(diagnosis|disease|condition)", re.IGNORECASE),"B-HEALTH", "DIAGNOSIS_FIELD", 90),

]
 
IGNORE_WORDS = {
    'gt', 'lt', 'mr', 'ms', 'dr', 'st', 'rd', 'th', 'nd', 'am', 'pm',
    'govt', 'government', 'india', 'indian', 'department', 'of', 'the',
    'ministry', 'office', 'card', 'number', 'date', 'name', 'male', 'female',
    'permanent', 'account', 'income', 'tax', 'signature', 'photo', 'valid',
    'app', 'keyword', 'search', 'this', 'sp', 'on', 'to', 'भारत', 'सरकार',
    'form', 'no', 'page', 'issue', 'code', 'type', 'class', 'श्री', 'एसो',
    'google', 'play', 'android', 'mobile', 'apple', 'store', 'qr', 'scan',
    'download', 'digitally', 'signe', 'signed', 'pan', 'aadhaar', 'gender',
    'dob', 'father', 'mother', 'address', 'birth'
}
 
NON_SENSITIVE_PHRASES = [
    'income tax', 'govt of india', 'government of india', 'permanent account',
    'signature', 'photo', 'department', 'ministry', 'आयकर', 'भारत सरकार',
    'date of birth', 'father name', 'mother name',
    'google play', 'android', 'mobile app', 'qr code', 'app store',
    'digitally sign', 'scan', 'download', 'apple', 'store'
]

ORG_KEYWORDS = {
    "department", "ministry", "hospital",
    "college", "university", "government",
    "bank", "insurance", "authority"
}
 
COLOR_MAP = {
    "B-DOC": (255, 0, 0, 180),
    "B-PER": (0, 0, 255, 180),
    "B-LOC": (0, 255, 0, 180),
    "B-DATE": (255, 165, 0, 180),
    "B-PHONE": (255, 0, 255, 180),
    "B-EMAIL": (0, 255, 255, 180),
    "B-FINANCIAL": (255, 255, 0, 180),
    "B-PHOTO": (148, 0, 211, 180),
    "B-QR": (75, 0, 130, 180),
}

# ==================== PRIVACY & DATA MANAGEMENT ====================
class PrivacyManager:
    """Manages privacy-preserving operations and data lifecycle."""
    
    def __init__(self, config: Dict):
        self.config = config
        self.session_id = self._generate_session_id()
        self.temp_files = []
    
    def _generate_session_id(self) -> str:
        """Generate anonymous session identifier."""
        timestamp = str(time.time()).encode()
        return hashlib.sha256(timestamp).hexdigest()[:16]
    
    def anonymize_text(self, text: str) -> str:
        """Replace actual PII with anonymized tokens."""
        if self.config.get("anonymize_feedback", True):
            for pattern in [
                r'\b[A-Z]{5}[0-9]{4}[A-Z]\b',
                r'\b\d{12}\b',
                r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            ]:
                text = re.sub(pattern, lambda m: f"[REDACTED_{hashlib.md5(m.group().encode()).hexdigest()[:8]}]", text)
        return text
    
    def register_temp_file(self, filepath: Path):
        """Track temporary files for cleanup."""
        self.temp_files.append(filepath)
    
    def cleanup_session(self):
        """Delete all temporary files from session."""
        for filepath in self.temp_files:
            try:
                if filepath.exists():
                    if filepath.is_file():
                        filepath.unlink()
                    elif filepath.is_dir():
                        shutil.rmtree(filepath)
                    print(f"[PRIVACY] Deleted: {filepath}")
            except Exception as e:
                print(f"[WARN] Failed to delete {filepath}: {e}")
        self.temp_files.clear()
    
    def cleanup_old_training_data(self):
        """Delete training data older than retention period."""
        if not self.config.get("auto_delete_training_data", True):
            return
        
        retention_days = self.config.get("retention_days", 7)
        cutoff_time = datetime.now() - timedelta(days=retention_days)
        
        deleted_count = 0
        for data_file in TRAINING_DIR.rglob("*.json"):
            try:
                mtime = datetime.fromtimestamp(data_file.stat().st_mtime)
                if mtime < cutoff_time:
                    data_file.unlink()
                    deleted_count += 1
            except Exception as e:
                print(f"[WARN] Failed to delete old training data: {e}")
        
        if deleted_count > 0:
            print(f"[PRIVACY] Deleted {deleted_count} old training files")
    
    def apply_differential_privacy(self, data: List[Dict]) -> List[Dict]:
        """Apply differential privacy to training data."""
        if not self.config.get("use_differential_privacy", True):
            return data
        
        epsilon = self.config.get("privacy_epsilon", 1.0)
        
        for item in data:
            if "score" in item:
                noise = np.random.laplace(0, 1.0 / epsilon)
                item["score"] = max(0, min(1, item["score"] + noise))
        
        return data

# ==================== CONFIDENCE CALIBRATION ====================
class ConfidenceCalibrator:
    """Calibrates and improves detection confidence scores."""
    
    def __init__(self):
        self.calibration_data = defaultdict(list)
        self.load_calibration_data()
    
    def load_calibration_data(self):
        """Load historical calibration data."""
        calib_file = MODEL_CACHE_DIR / "calibration.json"
        if calib_file.exists():
            try:
                with open(calib_file, 'r') as f:
                    data = json.load(f)
                    self.calibration_data = defaultdict(list, data)
                print(f"[CALIB] Loaded calibration data")
            except Exception as e:
                print(f"[WARN] Failed to load calibration: {e}")
    
    def save_calibration_data(self):
        """Save calibration data."""
        calib_file = MODEL_CACHE_DIR / "calibration.json"
        try:
            with open(calib_file, 'w') as f:
                json.dump(dict(self.calibration_data), f)
        except Exception as e:
            print(f"[WARN] Failed to save calibration: {e}")
    
    def calibrate_score(self, label: str, raw_score: float, pattern: str = None) -> float:
        """Calibrate confidence score based on historical performance."""
        key = f"{label}_{pattern}" if pattern else label
        
        if key in self.calibration_data and len(self.calibration_data[key]) > 10:
            history = self.calibration_data[key]
            avg_correction = np.mean([h['correction'] for h in history[-50:]])
            calibrated = raw_score + (avg_correction * 0.3)
            return max(0, min(1, calibrated))
        
        return raw_score
    
    def record_feedback(self, label: str, pattern: str, predicted_score: float, was_correct: bool):
        """Record user feedback for calibration."""
        key = f"{label}_{pattern}" if pattern else label
        correction = (1.0 - predicted_score) if was_correct else -predicted_score
        
        self.calibration_data[key].append({
            'score': predicted_score,
            'correct': was_correct,
            'correction': correction,
            'timestamp': time.time()
        })
        
        if len(self.calibration_data[key]) > 200:
            self.calibration_data[key] = self.calibration_data[key][-200:]
        
        self.save_calibration_data()

# ==================== VALIDATION ====================
def validate_aadhaar_checksum(aadhaar: str) -> bool:
    """Validate Aadhaar number using Verhoeff algorithm."""
    aadhaar = aadhaar.replace(" ", "").replace("-", "")
    if not aadhaar.isdigit() or len(aadhaar) != 12:
        return False
    
    d = [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
         [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
         [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
         [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
         [4, 0, 1, 2, 3, 9, 5, 6, 7, 8],
         [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
         [6, 5, 9, 8, 7, 1, 0, 4, 3, 2],
         [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
         [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
         [9, 8, 7, 6, 5, 4, 3, 2, 1, 0]]
    
    p = [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
         [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
         [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
         [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
         [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
         [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
         [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
         [7, 0, 4, 6, 9, 1, 3, 2, 5, 8]]
    
    c = 0
    for i, digit in enumerate(reversed(aadhaar)):
        c = d[c][p[(i % 8)][int(digit)]]
    
    return c == 0

def validate_pan_checksum(pan: str) -> bool:
    """Validate PAN format."""
    pan = pan.upper().strip()
    if len(pan) != 10:
        return False
    
    pattern = r'^[A-Z]{5}[0-9]{4}[A-Z]$'
    if not re.match(pattern, pan):
        return False
    
    return pan[3] in ['P', 'C', 'H', 'F', 'A', 'T', 'B', 'L', 'J', 'G']

# ==================== SELF-TRAINING SYSTEM ====================
class SelfTrainingSystem:

    def __init__(self, privacy_manager: PrivacyManager):
        self.privacy_manager = privacy_manager
        self.feedback_buffer = []

    # -------------------------------------------------
    # RECORD DETECTIONS
    # -------------------------------------------------
    def record_detection(self, detection: Dict, page_hash: str):

        features = detection.get("features", {})

        sample = {
            "page_hash": page_hash,
            "label": detection.get("label"),
            "pattern": detection.get("pattern"),
            "score": detection.get("score", 0.0),
            "features": features,
            "timestamp": time.time(),
            "session_id": self.privacy_manager.session_id
        }

        self.feedback_buffer.append(sample)

    # -------------------------------------------------
    # USER FEEDBACK
    # -------------------------------------------------
    def add_user_feedback(self, detection_index: int, is_correct: bool):

        if 0 <= detection_index < len(self.feedback_buffer):

            self.feedback_buffer[detection_index]["user_feedback"] = is_correct
            self.feedback_buffer[detection_index]["feedback_time"] = time.time()

            det = self.feedback_buffer[detection_index]

            if _CONFIDENCE_CALIBRATOR:
                _CONFIDENCE_CALIBRATOR.record_feedback(
                    det["label"],
                    det.get("pattern"),
                    det.get("score", 0.5),
                    is_correct
                )

    # -------------------------------------------------
    # MISSED DETECTIONS
    # -------------------------------------------------
    def add_missed_detection(self, word: str, label: str, page_hash: str):

        self.feedback_buffer.append({
            "page_hash": page_hash,
            "label": label,
            "pattern": "MISSED_ENTITY",
            "missed_detection": True,
            "timestamp": time.time(),
            "session_id": self.privacy_manager.session_id
        })

    # -------------------------------------------------
    # SAVE FEEDBACK
    # -------------------------------------------------
    def save_training_batch(self):

        if not self.feedback_buffer:
            return

        buffer_copy = self.privacy_manager.apply_differential_privacy(
            self.feedback_buffer.copy()
        )

        timestamp = int(time.time())
        filename = FEEDBACK_DIR / f"feedback_{timestamp}.json"

        with open(filename, "w") as f:
            json.dump(buffer_copy, f, indent=2, allow_nan=False)

        print(f"[TRAINING] Saved {len(buffer_copy)} samples to {filename}")

        self.feedback_buffer.clear()

    # -------------------------------------------------
    # TRAIN FROM FEEDBACK
    # -------------------------------------------------
    def train_from_feedback(self):

        feedback_files = list(FEEDBACK_DIR.glob("feedback_*.json"))

        if not feedback_files:
            print("[TRAINING] No feedback data available")
            return

        print(f"[TRAINING] Processing {len(feedback_files)} files...")

        label_stats = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})
        pattern_stats = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})

        X = []
        y = []

        # -------------------------------------------------
        # LOAD DATA
        # -------------------------------------------------
        for file in feedback_files:
            try:
                data = json.load(open(file))
            except:
                continue

            for item in data:

                label = item.get("label", "UNKNOWN")
                pattern = item.get("pattern") or "UNKNOWN"


                # ---- Supervised labels
                if "user_feedback" in item:

                    correct = item["user_feedback"]

                    if correct:
                        label_stats[label]["tp"] += 1
                        pattern_stats[pattern]["tp"] += 1
                    else:
                        label_stats[label]["fp"] += 1
                        pattern_stats[pattern]["fp"] += 1

                    # ML training
                    if "features" in item:
                        X.append(list(item["features"].values()))
                        y.append(1 if correct else 0)

                # ---- Missed detections
                if item.get("missed_detection"):
                    label_stats[label]["fn"] += 1
                    pattern_stats[pattern]["fn"] += 1

        print("\n[TRAINING] Aggregated Feedback Statistics")
        print("=" * 70)

        # -------------------------------------------------
        # LABEL METRICS
        # -------------------------------------------------
        adaptive_threshold_file = MODEL_CACHE_DIR / "adaptive_thresholds.json"
        adaptive_thresholds = {}

        if adaptive_threshold_file.exists():
            adaptive_thresholds = json.load(open(adaptive_threshold_file))

        print("\n[Label Metrics]")

        for label, stats in sorted(label_stats.items()):

            tp = stats["tp"]
            fp = stats["fp"]
            fn = stats["fn"]

            precision = tp / (tp + fp) if (tp + fp) > 0 else 0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0

            print(f"  {label:15s} | P={precision:.2f} R={recall:.2f}")

            # Strict control for noisy B-LOC
            if label == "B-LOC" and precision < 0.40:
                adaptive_thresholds[label] = 0.30

        json.dump(adaptive_thresholds, open(adaptive_threshold_file, "w"), indent=2)

        # -------------------------------------------------
        # PATTERN DISABLING
        # -------------------------------------------------
        pattern_file = MODEL_CACHE_DIR / "disabled_patterns.json"
        disabled_patterns = []

        if pattern_file.exists():
            disabled_patterns = json.load(open(pattern_file))

        print("\n[Pattern Metrics]")

        for pattern, stats in sorted(pattern_stats.items(), key=lambda x: str(x[0])):

            tp = stats["tp"]
            fp = stats["fp"]
            fn = stats["fn"]

            precision = tp / (tp + fp) if (tp + fp) > 0 else 0

            print(f"  {pattern:20s} | P={precision:.2f}")

            if precision < 0.40 and (tp + fp) >= 5:
                disabled_patterns.append(pattern)

        disabled_patterns = list(set(disabled_patterns))
        json.dump(disabled_patterns, open(pattern_file, "w"), indent=2)

        # -------------------------------------------------
        # TRAIN ML GATING MODEL
        # -------------------------------------------------
        if len(X) >= 20:

            print("\n[ML] Training gating model...")

            clf = LogisticRegression(max_iter=1000)
            clf.fit(X, y)

            model_path = MODEL_CACHE_DIR / "gating_model.pkl"
            joblib.dump(clf, model_path)

            print("[ML] Gating model saved")

        else:
            print("\n[ML] Not enough data for ML gating (need ~20 samples)")

        print("\n[TRAINING COMPLETE]")
        print("=" * 70)



 
# ==================== UTILITY FUNCTIONS ====================
def now_ts() -> str:
    return str(int(time.time()))
 
def normalize_tesseract_lang(lang_str: str) -> str:
    """Convert language codes to Tesseract format."""
    if not lang_str:
        return "eng"
    
    lang_map = {
        'en': 'eng', 'hi': 'hin', 'zh': 'chi_sim', 'es': 'spa',
        'fr': 'fra', 'de': 'deu', 'it': 'ita', 'ja': 'jpn',
    }
    
    parts = re.split(r'[+\s]', lang_str)
    converted = []
    
    for part in parts:
        part_clean = part.strip().lower()
        if not part_clean:
            continue
        if len(part_clean) == 2 and part_clean in lang_map:
            converted.append(lang_map[part_clean])
        else:
            converted.append(part_clean)
    
    return '+'.join(converted) if converted else 'eng'
 
def validate_bbox(bbox: List[int], image_size: Tuple[int, int]) -> Optional[List[int]]:
    """Validate and fix bounding box coordinates with size limits."""
    if not bbox or len(bbox) != 4:
        return None
    
    x0, y0, x1, y1 = bbox
    img_w, img_h = image_size
    
    x0, x1 = sorted([int(x0), int(x1)])
    y0, y1 = sorted([int(y0), int(y1)])
    
    x0 = max(0, min(x0, img_w - 1))
    y0 = max(0, min(y0, img_h - 1))
    x1 = max(0, min(x1, img_w))
    y1 = max(0, min(y1, img_h))
    
    w = x1 - x0
    h = y1 - y0
    
    if w < MIN_BOX_WH or h < MIN_BOX_WH:
        return None
    
    if w > MAX_BOX_WIDTH or h > MAX_BOX_HEIGHT:
        return None
    
    area = w * h
    if area > MAX_BOX_AREA:
        return None
    
    aspect = max(w, h) / max(min(w, h), 1)
    if aspect > 30:
        return None
    
    return [x0, y0, x1, y1]
 
def expand_bbox(bbox: List[int], image_size: Tuple[int, int], pad: int = PAD_PIXELS) -> List[int]:
    """Expand bbox with padding."""
    x0, y0, x1, y1 = bbox
    img_w, img_h = image_size
    
    x0 = max(0, x0 - pad)
    y0 = max(0, y0 - pad)
    x1 = min(img_w, x1 + pad)
    y1 = min(img_h, y1 + pad)
    
    return [int(x0), int(y0), int(x1), int(y1)]
 
def bbox_iou(box1: List[int], box2: List[int]) -> float:
    """Calculate IoU between two bounding boxes."""
    x0 = max(box1[0], box2[0])
    y0 = max(box1[1], box2[1])
    x1 = min(box1[2], box2[2])
    y1 = min(box1[3], box2[3])
    
    inter_area = max(0, x1 - x0) * max(0, y1 - y0)
    area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
    area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
    union_area = area1 + area2 - inter_area
    
    return inter_area / union_area if union_area > 0 else 0
 
def is_non_sensitive_text(text: str) -> bool:
    """Check if text is a common header/footer/label."""
    text_lower = text.lower().strip()
    
    if len(text_lower) < 2:
        return True
    
    if text_lower in IGNORE_WORDS:
        return True
    
    for phrase in NON_SENSITIVE_PHRASES:
        if phrase in text_lower:
            return True
    
    return False

# ==================== IMAGE ROTATION DETECTION ====================
def detect_and_fix_orientation(pil_img: Image.Image) -> Tuple[Image.Image, int]:
    """Detect and fix image orientation using Tesseract OSD."""
    try:
        osd_data = pytesseract.image_to_osd(pil_img)
        
        rotation = 0
        for line in osd_data.split('\n'):
            if 'Rotate:' in line:
                rotation = int(line.split(':')[1].strip())
                break
        
        if rotation != 0:
            print(f"[ROTATION] Detected {rotation}° rotation, correcting...")
            if rotation == 90:
                pil_img = pil_img.rotate(-90, expand=True)
            elif rotation == 180:
                pil_img = pil_img.rotate(-180, expand=True)
            elif rotation == 270:
                pil_img = pil_img.rotate(-270, expand=True)
            
            return pil_img, rotation
        
        return pil_img, 0
        
    except Exception as e:
        print(f"[WARN] OSD detection failed: {e}, trying manual rotation...")
        return try_best_orientation(pil_img)

def try_best_orientation(pil_img: Image.Image) -> Tuple[Image.Image, int]:
    """Try different orientations and return best one based on OCR confidence."""
    orientations = [
        (pil_img, 0),
        (pil_img.rotate(-90, expand=True), 90),
        (pil_img.rotate(-180, expand=True), 180),
        (pil_img.rotate(-270, expand=True), 270)
    ]
    
    best_img = pil_img
    best_rotation = 0
    best_confidence = 0
    
    for img, rotation in orientations:
        try:
            data = pytesseract.image_to_data(img, output_type=Output.DICT, config='--psm 6')
            confidences = [c for c in data.get('conf', []) if c != -1]
            avg_conf = sum(confidences) / len(confidences) if confidences else 0
            
            if avg_conf > best_confidence:
                best_confidence = avg_conf
                best_img = img
                best_rotation = rotation
        except:
            continue
    
    if best_rotation != 0:
        print(f"[ROTATION] Best orientation: {best_rotation}° (confidence: {best_confidence:.1f})")
    
    return best_img, best_rotation
 
# ==================== PDF & OCR ====================
def pdf_to_images(pdf_path: str, dpi: int = PDF_DPI) -> List[Image.Image]:
    """Convert PDF to images."""
    try:
        pages = convert_from_path(pdf_path, dpi=dpi)
        return [p.convert("RGB") for p in pages]
    except Exception as e:
        print(f"[ERROR] Failed to convert PDF: {e}")
        raise
 
def preprocess_for_ocr(pil_img: Image.Image) -> Image.Image:
    """Preprocess image for OCR."""
    img = pil_img.convert("RGB")
    
    max_dim = 3500
    if max(img.width, img.height) > max_dim:
        scale = max_dim / max(img.width, img.height)
        new_w = int(img.width * scale)
        new_h = int(img.height * scale)
        img = img.resize((new_w, new_h), Image.LANCZOS)
    
    gray = ImageOps.grayscale(img)
    gray = ImageOps.autocontrast(gray, cutoff=2)
    
    return gray
 
def ocr_tesseract(pil_img: Image.Image, lang: str = "eng") -> Tuple[str, List[Dict]]:
    """OCR using Tesseract."""
    img_proc = preprocess_for_ocr(pil_img)
    lang_normalized = normalize_tesseract_lang(lang)
    print(f"[OCR] Tesseract with '{lang_normalized}'")
    
    config = f"-l {lang_normalized} --oem {OCR_OEM} --psm {OCR_PSM}"
    
    try:
        data = pytesseract.image_to_data(img_proc, output_type=Output.DICT, config=config)
    except:
        config = f"-l eng --oem {OCR_OEM} --psm {OCR_PSM}"
        data = pytesseract.image_to_data(img_proc, output_type=Output.DICT, config=config)
    
    tokens = []
    image_size = (pil_img.width, pil_img.height)
    
    for i, txt in enumerate(data.get("text", [])):
        if not txt or not str(txt).strip():
            continue
        
        try:
            left = int(data["left"][i])
            top = int(data["top"][i])
            w = int(data["width"][i])
            h = int(data["height"][i])
            conf = float(data.get("conf", [0])[i])
            
            bbox = validate_bbox([left, top, left + w, top + h], image_size)
            if bbox:
                tokens.append({
                    "text": txt,
                    "left": bbox[0],
                    "top": bbox[1],
                    "width": bbox[2] - bbox[0],
                    "height": bbox[3] - bbox[1],
                    "conf": conf,
                    "source": "tesseract"
                })
        except:
            continue
    
    print(f"[OCR] Tesseract: {len(tokens)} tokens")
    return " ".join(t["text"] for t in tokens), tokens
 
def ocr_easyocr(pil_img: Image.Image, lang_list: List[str]) -> Tuple[str, List[Dict]]:
    """OCR using EasyOCR."""
    global _EASYOCR_READER
    
    try:
        if _EASYOCR_READER is None:
            import easyocr
            print(f"[OCR] Loading EasyOCR: {lang_list}")
            _EASYOCR_READER = easyocr.Reader(lang_list, gpu=torch.cuda.is_available())
        
        img_np = np.array(pil_img)
        results = _EASYOCR_READER.readtext(img_np)
        
        tokens = []
        image_size = (pil_img.width, pil_img.height)
        
        for detection in results:
            bbox_coords, text, conf = detection
            xs = [pt[0] for pt in bbox_coords]
            ys = [pt[1] for pt in bbox_coords]
            
            x0, y0 = int(min(xs)), int(min(ys))
            x1, y1 = int(max(xs)), int(max(ys))
            
            bbox = validate_bbox([x0, y0, x1, y1], image_size)
            if bbox:
                tokens.append({
                    "text": text,
                    "left": bbox[0],
                    "top": bbox[1],
                    "width": bbox[2] - bbox[0],
                    "height": bbox[3] - bbox[1],
                    "conf": conf * 100,
                    "source": "easyocr"
                })
        
        print(f"[OCR] EasyOCR: {len(tokens)} tokens")
        return " ".join(t["text"] for t in tokens), tokens
        
    except ImportError:
        print("[WARN] EasyOCR not installed, skipping")
        return "", []
    except Exception as e:
        print(f"[WARN] EasyOCR failed: {e}")
        return "", []
 
def deduplicate_tokens(tokens: List[Dict]) -> List[Dict]:
    """Remove duplicate tokens."""
    if not tokens:
        return []
    
    sorted_tokens = sorted(tokens, key=lambda t: t.get("conf", 0), reverse=True)
    kept = []
    
    for token in sorted_tokens:
        bbox = [token["left"], token["top"], 
                token["left"] + token["width"], 
                token["top"] + token["height"]]
        
        is_duplicate = False
        for kept_token in kept:
            kept_bbox = [kept_token["left"], kept_token["top"],
                        kept_token["left"] + kept_token["width"],
                        kept_token["top"] + kept_token["height"]]
            
            iou = bbox_iou(bbox, kept_bbox)
            text_similar = fuzz.ratio(token.get("text", "").lower(), 
                                     kept_token.get("text", "").lower()) > 80
            
            if iou > 0.7 and text_similar:
                is_duplicate = True
                break
        
        if not is_duplicate:
            kept.append(token)
    
    return kept
 
def ocr_multi_engine(pil_img: Image.Image, lang: str = "eng") -> Tuple[str, List[Dict]]:
    """Run ALL configured OCR engines."""
    all_tokens = []
    all_texts = []
    
    print(f"[OCR] Running {len(OCR_ENGINES)} engine(s): {', '.join(OCR_ENGINES)}")
    
    if "tesseract" in OCR_ENGINES:
        tess_text, tess_tokens = ocr_tesseract(pil_img, lang)
        if tess_tokens:
            all_tokens.extend(tess_tokens)
            all_texts.append(tess_text)
    
    if "easyocr" in OCR_ENGINES:
        easy_langs = []
        if 'eng' in lang or 'en' in lang:
            easy_langs.append('en')
        if 'hin' in lang or 'hi' in lang:
            easy_langs.append('hi')
        if not easy_langs:
            easy_langs = ['en']
        
        easy_text, easy_tokens = ocr_easyocr(pil_img, easy_langs)
        if easy_tokens:
            all_tokens.extend(easy_tokens)
            all_texts.append(easy_text)
    
    unique_tokens = deduplicate_tokens(all_tokens)
    combined_text = " ".join(all_texts)
    
    print(f"[OCR] Combined: {len(unique_tokens)} unique tokens")
    return combined_text, unique_tokens
 
# ==================== NER ====================
def load_ner_pipelines():
    """Load ALL configured NER models with proper configuration."""
    global _NER_PIPELINES, _NER_LOADED
    if _NER_LOADED:
        return _NER_PIPELINES
    
    device = 0 if torch.cuda.is_available() else -1
    pipes = []
    
    print(f"[NER] Loading {len(AI_MODELS)} model(s)...")
    for i, model_name in enumerate(AI_MODELS, 1):
        try:
            print(f"[NER] [{i}/{len(AI_MODELS)}] Loading {model_name}...")
            p = pipeline(
                "ner", 
                model=model_name, 
                aggregation_strategy="simple", 
                device=device
            )
            pipes.append(p)
            print(f"[NER] [{i}/{len(AI_MODELS)}] ✓ Loaded successfully")
        except Exception as e:
            print(f"[WARN] [{i}/{len(AI_MODELS)}] ✗ Failed to load {model_name}: {e}")
    
    if not pipes:
        print("[ERROR] No NER models loaded! Detection will be limited.")
    else:
        print(f"[NER] Successfully loaded {len(pipes)}/{len(AI_MODELS)} model(s)")
    
    _NER_PIPELINES = pipes
    _NER_LOADED = True
    return _NER_PIPELINES
 
def canonicalize_label(label_str: str) -> str:
    """Normalize entity labels - EXCLUDE B-MISC and B-ORG."""
    s = str(label_str).upper()
    if s in ("O", "0"):
        return "O"
    
    if "MISC" in s or "ORG" in s:
        return "O"
    
    if any(x in s for x in ["PAN", "DOC", "PASSPORT", "ID", "SSN", "AADHAAR"]):
        return "B-DOC"
    if any(x in s for x in ["PER", "NAME", "PERSON"]):
        return "B-PER"
    if any(x in s for x in ["LOC", "CITY", "STATE", "ADDRESS"]):
        return "B-LOC"
    if any(x in s for x in ["DATE", "DOB", "BIRTH"]):
        return "B-DATE"
    if any(x in s for x in ["PHONE", "MOBILE"]):
        return "B-PHONE"
    if "EMAIL" in s:
        return "B-EMAIL"
    
    return "O"
 
def run_ner(text: str) -> List[Dict]:
    """
    Run ALL configured NER models with ensemble voting.
    Improves precision and reduces hallucinated entities.
    """

    pipes = load_ner_pipelines()
    if not pipes:
        print("[WARN] No NER models available")
        return []

    all_preds = []

    for i, p in enumerate(pipes, 1):
        try:
            print(f"[NER] Running model {i}/{len(pipes)}...")
            text_chunk = text[:5000] if len(text) > 5000 else text
            preds = p(text_chunk)
            all_preds.extend(preds)
            print(f"[NER] Model {i}/{len(pipes)}: {len(preds)} predictions")
        except Exception as e:
            print(f"[WARN] NER model {i}/{len(pipes)} failed: {e}")

    print(f"[NER] Raw predictions from all models: {len(all_preds)}")

    # ===============================
    # ENSEMBLE VOTING MECHANISM
    # ===============================

    entity_counter = defaultdict(list)

    for pred in all_preds:
        word = pred.get("word")
        entity = pred.get("entity_group", pred.get("entity"))
        score = pred.get("score", 0)

        if not word or not entity:
            continue

        key = (word.strip(), entity)
        entity_counter[key].append(score)

    filtered_preds = []

    for (word, entity), scores in entity_counter.items():

        max_score = max(scores)
        avg_score = float(np.mean(scores))
        vote_count = len(scores)

        # ===== RULES =====
        # 1. Keep if 2+ models agree
        # 2. OR if single model extremely confident
        if vote_count >= 2 or max_score > 0.85:
            filtered_preds.append({
                "word": word,
                "entity_group": entity,
                "score": avg_score
            })

    print(f"[NER] After ensemble voting: {len(filtered_preds)} predictions")

    return filtered_preds
 
def map_ner_to_tokens(
    ner_preds: List[Dict],
    tokens: List[Dict],
    full_text: str,
    image_size: Tuple[int, int]
) -> List[Dict]:
    """
    High-precision NER-to-OCR mapping.
    - Adaptive thresholds
    - Strict label filtering
    - MRZ suppression
    - False-positive reduction
    """

    detections = []

    # -----------------------------------
    # Load adaptive threshold shifts
    # -----------------------------------
    adaptive_thresholds = {}
    adaptive_file = MODEL_CACHE_DIR / "adaptive_thresholds.json"

    if adaptive_file.exists():
        try:
            with open(adaptive_file, "r") as f:
                adaptive_thresholds = json.load(f)
        except:
            adaptive_thresholds = {}

    token_texts = [t["text"] for t in tokens]
    joined = " ".join(token_texts).lower()

    for pred in ner_preds:

        word = pred.get("word", "").strip()

        # Basic filtering
        if not word or len(word) <= 2:
            continue

        if any(char.isdigit() for char in word):
            continue  # prevent numeric hallucinations

        if is_non_sensitive_text(word):
            continue

        label = canonicalize_label(
            pred.get("entity_group", pred.get("entity", "O"))
        )

        if label == "O":
            continue

        score = float(pred.get("score", 0.0))

        # -----------------------------------
        # STRICT LABEL THRESHOLDS
        # -----------------------------------
        if label == "B-PER":
            base_threshold = 0.60
        elif label == "B-LOC":
            base_threshold = 0.82
        elif label == "B-DATE":
            base_threshold = 0.75
        else:
            base_threshold = 0.70

        shift = adaptive_thresholds.get(label, 0.0)
        adjusted_threshold = max(0.2, min(0.95, base_threshold + shift))

        if score < adjusted_threshold:
            continue

        word_lower = word.lower()

        if word_lower not in joined:
            continue

        # -----------------------------------
        # MRZ SUPPRESSION
        # -----------------------------------
        # Ignore NER results in bottom 25% unless very confident
        for token in tokens:
            if word_lower in token.get("text", "").lower():
                if token["top"] > image_size[1] * 0.75 and score < 0.90:
                    continue

        # -----------------------------------
        # Span Alignment
        # -----------------------------------
        idx = joined.find(word_lower)
        cum = 0
        start_idx = None
        end_idx = None

        for i, t in enumerate(token_texts):
            t_low = t.lower()

            if start_idx is None and cum + len(t_low) > idx:
                start_idx = i

            if start_idx is not None:
                span_text = " ".join(token_texts[start_idx:i + 1]).lower()

                if span_text.startswith(word_lower):
                    end_idx = i
                    break

            cum += len(t_low) + 1

        if start_idx is None or end_idx is None:
            continue

        # -----------------------------------
        # Bounding Box Merge
        # -----------------------------------
        xs = [tokens[j]["left"] for j in range(start_idx, end_idx + 1)]
        ys = [tokens[j]["top"] for j in range(start_idx, end_idx + 1)]
        x2s = [tokens[j]["left"] + tokens[j]["width"] for j in range(start_idx, end_idx + 1)]
        y2s = [tokens[j]["top"] + tokens[j]["height"] for j in range(start_idx, end_idx + 1)]

        bbox = validate_bbox(
            [min(xs), min(ys), max(x2s), max(y2s)],
            image_size
        )

        if not bbox:
            continue

        # -----------------------------------
        # Location False Positive Filter
        # -----------------------------------
        if label == "B-LOC":
            if word.upper() in IGNORE_WORDS:
                continue

            # Reject single short ambiguous words
            if len(word.split()) == 1 and len(word) < 5:
                continue

        detections.append({
            "word": " ".join(token_texts[start_idx:end_idx + 1]),
            "bbox": bbox,
            "label": label,
            "score": score,
            "priority": 75
        })

    return detections
 
def detect_capitalized_names(tokens: List[Dict], image_size: Tuple[int, int]) -> List[Dict]:
    """
    Precision-focused capitalized name detector.
    Designed to reduce false positives significantly.
    """

    detections = []

    # Words that should NEVER be treated as names
    STOPWORDS = {
        "REPUBLIC", "INDIA", "PLACE", "NAME", "SURNAME",
        "PASSPORT", "GOVERNMENT", "DATE", "BIRTH",
        "FATHER", "MOTHER", "LEGAL", "GUARDIAN",
        "HOLDER", "SIGNATURE", "ADDRESS",
        "OF", "THE", "AND"
    }

    i = 0
    while i < len(tokens):

        token = tokens[i]
        text = token.get("text", "").strip()

        if not text:
            i += 1
            continue

        # Basic filters
        if (
            len(text) < 3 or
            text.upper() in STOPWORDS or
            any(c.isdigit() for c in text) or
            not text.isalpha() or
            not text.isupper()
        ):
            i += 1
            continue

        # Avoid MRZ zone (bottom 25%)
        if token["top"] > image_size[1] * 0.75:
            i += 1
            continue

        # Collect consecutive uppercase tokens
        name_tokens = [token]

        for j in range(i + 1, min(i + 5, len(tokens))):
            next_token = tokens[j]
            next_text = next_token.get("text", "").strip()

            if (
                next_text.isupper() and
                next_text.isalpha() and
                next_text not in STOPWORDS and
                abs(next_token["top"] - token["top"]) < 15
            ):
                name_tokens.append(next_token)
            else:
                break

        # Require at least 2 tokens for valid name
        if 2 <= len(name_tokens) <= 4:

            full_name = " ".join(t["text"] for t in name_tokens)

            # Reject suspicious OCR garbage
            if len(full_name) > 40:
                i += len(name_tokens)
                continue

            # Merge bounding boxes
            xs = [t["left"] for t in name_tokens]
            ys = [t["top"] for t in name_tokens]
            x2s = [t["left"] + t["width"] for t in name_tokens]
            y2s = [t["top"] + t["height"] for t in name_tokens]

            bbox = validate_bbox(
                [min(xs), min(ys), max(x2s), max(y2s)],
                image_size
            )

            if bbox:
                detections.append({
                    "word": full_name,
                    "bbox": bbox,
                    "label": "B-PER",
                    "pattern": "CAPITALIZED_NAME",
                    "priority": 80,
                })

            i += len(name_tokens)
        else:
            i += 1

    return detections


def detect_name_field_context(tokens: List[Dict], image_size: Tuple[int, int]) -> List[Dict]:
    """Detect ALL capitalized words near 'Name' label."""
    detections = []
    
    name_label_positions = []
    for i, token in enumerate(tokens):
        text = token.get("text", "").strip().lower()
        if text in ['name', 'नाम', 'name:', 'surname', 'given']:
            name_label_positions.append({
                'index': i,
                'top': token['top'],
                'height': token['height'],
                'left': token['left'],
                'right': token['left'] + token['width']
            })
    
    if not name_label_positions:
        return detections
    
    for name_pos in name_label_positions:
        name_line_tokens = []
        
        for i, token in enumerate(tokens):
            text = token.get("text", "").strip()
            
            if not text or len(text) < 3:
                continue
            
            token_top = token.get("top", 0)
            vert_dist = abs(token_top - name_pos['top'])
            
            if vert_dist <= max(15, name_pos['height'] * 0.7):
                if (text[0].isupper() and 
                    sum(c.isalpha() for c in text) >= len(text) * 0.7 and
                    not is_non_sensitive_text(text) and
                    text.lower() not in ['name', 'नाम', 'surname', 'given']):
                    
                    token_left = token.get("left", 0)
                    if token_left > name_pos['right'] or token_left < name_pos['left'] - 100:
                        name_line_tokens.append(token)
        
        for token in name_line_tokens:
            bbox = [
                token["left"],
                token["top"],
                token["left"] + token["width"],
                token["top"] + token["height"]
            ]
            bbox = validate_bbox(bbox, image_size)
            
            if bbox:
                detections.append({
                    "word": token.get("text", ""),
                    "bbox": bbox,
                    "label": "B-PER",
                    "pattern": "NAME_FIELD_CONTEXT",
                    "priority": 92,
                })
    
    return detections
 
# ==================== VISUAL DETECTION ====================
def detect_photos(pil_img: Image.Image) -> List[Dict]:
    """Detect photos/faces."""
    detections = []
    
    try:
        img_np = np.array(pil_img)
        gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
        
        face_cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        face_cascade = cv2.CascadeClassifier(face_cascade_path)
        
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
        print(f"[VISUAL] Detected {len(faces)} face(s)")
        
        for (x, y, w, h) in faces:
            pad = 10
            x0 = max(0, x - pad)
            y0 = max(0, y - pad)
            x1 = min(pil_img.width, x + w + pad)
            y1 = min(pil_img.height, y + h + pad)
            
            bbox = validate_bbox([x0, y0, x1, y1], (pil_img.width, pil_img.height))
            if bbox:
                detections.append({
                    "word": "[PHOTO]",
                    "bbox": bbox,
                    "label": "B-PHOTO",
                    "pattern": "PHOTO",
                    "priority": 95,
                })
    except Exception as e:
        print(f"[WARN] Face detection failed: {e}")
    
    return detections
 
def detect_qr_codes(pil_img: Image.Image) -> List[Dict]:
    """Detect QR codes."""
    detections = []
    
    try:
        from pyzbar import pyzbar
        img_np = np.array(pil_img)
        decoded = pyzbar.decode(img_np)
        
        print(f"[VISUAL] Detected {len(decoded)} QR/barcode(s)")
        
        for obj in decoded:
            x, y, w, h = obj.rect
            pad = 8
            x0 = max(0, x - pad)
            y0 = max(0, y - pad)
            x1 = min(pil_img.width, x + w + pad)
            y1 = min(pil_img.height, y + h + pad)
            
            bbox = validate_bbox([x0, y0, x1, y1], (pil_img.width, pil_img.height))
            if bbox:
                detections.append({
                    "word": f"[{obj.type}]",
                    "bbox": bbox,
                    "label": "B-QR",
                    "pattern": "QR_CODE",
                    "priority": 90,
                })
    except:
        pass
    
    return detections
 
# ==================== REDACTION ====================
def inpaint_redaction(pil_img: Image.Image, detections: List[Dict]) -> Image.Image:
    """
    OpenCV Telea inpainting redaction.
    Most natural visual result.
    """

    img_np = np.array(pil_img)
    mask = np.zeros(img_np.shape[:2], dtype=np.uint8)

    image_size = (pil_img.width, pil_img.height)

    for det in detections:
        bbox = det.get("bbox")
        if not bbox:
            continue

        bbox = validate_bbox(bbox, image_size)
        if not bbox:
            continue

        bbox = expand_bbox(bbox, image_size, pad=PAD_PIXELS)
        x0, y0, x1, y1 = bbox

        mask[y0:y1, x0:x1] = 255

    # Telea algorithm
    inpainted = cv2.inpaint(img_np, mask, 15, cv2.INPAINT_TELEA)

    print(f"[REDACT] Applied {len(detections)} inpaint redactions (Level 4)")
    return Image.fromarray(inpainted)

def redact_image(pil_img: Image.Image, detections: List[Dict], level: int = 2) -> Image.Image:
    """
    Progressive redaction system.
    Level 1 → Blur
    Level 2 → Mask (black box)
    Level 3 → Synth (white + placeholder)
    Level 4 → Inpaint (OpenCV reconstruction)
    """


    # Level 4 handled separately
    if level == 4:
        return inpaint_redaction(pil_img, detections)

    img = pil_img.copy().convert("RGB")
    draw = ImageDraw.Draw(img)
    image_size = (img.width, img.height)

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
    except:
        font = ImageFont.truetype("arial.ttf", 14)

    redacted_count = 0

    for det in detections:
        bbox = det.get("bbox")
        if not bbox:
            continue

        bbox = validate_bbox(bbox, image_size)
        if not bbox:
            continue

        bbox = expand_bbox(bbox, image_size, pad=PAD_PIXELS)
        x0, y0, x1, y1 = bbox

        if x1 <= x0 or y1 <= y0:
            continue

        if det.get("label") in ["B-HEALTH", "B-DOC"]:
            draw.rectangle([x0, y0, x1, y1], fill=(0, 0, 0))
            redacted_count += 1
            continue
        # -------- LEVEL 1: BLUR --------
        if level == 1:
            region = img.crop((x0, y0, x1, y1))
            region = region.filter(ImageFilter.GaussianBlur(radius=10))
            img.paste(region, (x0, y0))
            redacted_count += 1

        # -------- LEVEL 2: MASK --------
        elif level == 2:
            draw.rectangle([x0, y0, x1, y1], fill=(0, 0, 0))
            redacted_count += 1

        # -------- LEVEL 3: SYNTH --------
        elif level == 3:
            draw.rectangle([x0, y0, x1, y1], fill=(255, 255, 255), outline=(200, 200, 200))
            synth_text = "█" * min(8, (x1 - x0) // 8)
            draw.text((x0 + 2, y0 + 2), synth_text, fill=(0, 0, 0), font=font)
            redacted_count += 1

    print(f"[REDACT] Applied {redacted_count} redactions (Level {level})")
    return img
 
def save_debug_visualization(pil_img: Image.Image, detections: List[Dict], output_path: Path):
    """Save debug visualization."""
    img = pil_img.copy().convert("RGB")
    draw = ImageDraw.Draw(img, 'RGBA')
    
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 12)
    except:
        font = ImageFont.load_default()
    
    image_size = (img.width, img.height)
    
    for i, det in enumerate(detections):
        bbox = det.get("bbox")
        if not bbox:
            continue
        
        bbox = validate_bbox(bbox, image_size)
        if not bbox:
            continue
        
        bbox = expand_bbox(bbox, image_size, pad=PAD_PIXELS)
        x0, y0, x1, y1 = bbox
        
        label = det.get("label", "O")
        pattern = det.get("pattern", "")
        
        color = COLOR_MAP.get(label, (128, 128, 128, 180))
        
        draw.rectangle([x0, y0, x1, y1], outline=color[:3], width=2)
        label_text = f"{i+1}:{pattern or label}"
        draw.text((x0, max(0, y0 - 15)), label_text, fill=color[:3], font=font)
    
    img.save(output_path)
    print(f"[DEBUG] Saved: {output_path}")
 
# ==================== REPORTING ====================
def generate_report(all_pages_detections: List[List[Dict]], output_path: Path):
    """Generate report."""
    lines = []
    lines.append("=" * 70)
    lines.append("REDACTION SUMMARY REPORT")
    lines.append("=" * 70)
    lines.append(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Total Pages: {len(all_pages_detections)}")
    lines.append("")
    
    total_redactions = sum(len(dets) for dets in all_pages_detections)
    pattern_counts = defaultdict(int)
    
    for page_dets in all_pages_detections:
        for det in page_dets:
            pattern = det.get("pattern", det.get("label", "UNKNOWN"))
            pattern_counts[pattern] += 1
    
    lines.append("OVERALL STATISTICS")
    lines.append("-" * 70)
    lines.append(f"Total Redactions: {total_redactions}")
    lines.append("")
    lines.append("Redactions by Type:")
    for pattern, count in sorted(pattern_counts.items(), key=lambda x: x[1], reverse=True):
        lines.append(f"  {pattern:20s}: {count:3d}")
    lines.append("")
    
    lines.append("PER-PAGE BREAKDOWN")
    lines.append("-" * 70)
    
    for page_no, dets in enumerate(all_pages_detections, 1):
        lines.append(f"\nPage {page_no}: {len(dets)} redactions")
        
        if dets:
            page_patterns = defaultdict(list)
            for det in dets:
                pattern = det.get("pattern", det.get("label", "UNKNOWN"))
                word_preview = det.get("word", "")[:30]
                page_patterns[pattern].append(word_preview)
            
            for pattern, words in sorted(page_patterns.items()):
                lines.append(f"  {pattern}:")
                for word in words[:3]:
                    lines.append(f"    - {word}")
                if len(words) > 3:
                    lines.append(f"    ... and {len(words) - 3} more")
    
    lines.append("")
    lines.append("=" * 70)
    
    report_text = "\n".join(lines)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_text)
    
    print(f"\n[INFO] Report saved: {output_path}")
 
# ==================== MAIN PROCESSING ====================
def detect_passport_mrz(tokens: List[Dict], image_size: Tuple[int, int]) -> List[Dict]:

    detections = []

    for token in tokens:
        text = token.get("text", "").strip()

        if (
            len(text) > 25 and
            text.isupper() and
            "<" in text and
            MRZ_PATTERN.fullmatch(text)
        ):
            bbox = validate_bbox([
                token["left"],
                token["top"],
                token["left"] + token["width"],
                token["top"] + token["height"]
            ], image_size)

            if bbox:
                detections.append({
                    "word": text,
                    "bbox": bbox,
                    "label": "B-DOC",
                    "pattern": "PASSPORT_MRZ",
                    "priority": 120
                })

    return detections

def extract_detection_features(det: Dict, image_size: Tuple[int, int]) -> Dict:
    """
    Convert detection into ML features for gating classifier.
    """

    x0, y0, x1, y1 = det.get("bbox", [0, 0, 0, 0])
    width = x1 - x0
    height = y1 - y0

    page_w, page_h = image_size

    word = det.get("word", "")

    features = {
        "score": det.get("score", 0.5),
        "priority": det.get("priority", 0),
        "rel_x": x0 / page_w if page_w else 0,
        "rel_y": y0 / page_h if page_h else 0,
        "rel_width": width / page_w if page_w else 0,
        "rel_height": height / page_h if page_h else 0,
        "word_len": len(word),
        "is_upper": int(word.isupper()),
        "has_digit": int(any(c.isdigit() for c in word)),
        "num_tokens": len(word.split()),
        "label_id": hash(det.get("label", "")) % 1000
    }

    return features

def process_page(pil_img: Image.Image, page_no: int, args) -> Tuple[Image.Image, List[Dict]]:

    global _CONFIDENCE_CALIBRATOR, _TRAINING_SYSTEM

    if _CONFIDENCE_CALIBRATOR is None:
        _CONFIDENCE_CALIBRATOR = ConfidenceCalibrator()

    print(f"\n{'='*70}")
    print(f"PAGE {page_no}")
    print(f"{'='*70}")
    print(f"Size: {pil_img.width}x{pil_img.height}")

    page_hash = hashlib.md5(pil_img.tobytes()).hexdigest()[:16]

    # -------------------------------------------------
    # Orientation Fix
    # -------------------------------------------------
    pil_img, rotation = detect_and_fix_orientation(pil_img)
    if rotation != 0:
        print(f"[INFO] Applied {rotation}° rotation correction")

    # -------------------------------------------------
    # OCR
    # -------------------------------------------------
    full_text, tokens = ocr_multi_engine(pil_img, lang=args.lang)
    print(f"[INFO] Tokens: {len(tokens)}")

    if not tokens:
        return pil_img, []

    image_size = (pil_img.width, pil_img.height)

    # -------------------------------------------------
    # Passport MRZ Detection
    # -------------------------------------------------
    mrz_detections = detect_passport_mrz(tokens, image_size)

    # -------------------------------------------------
    # NER
    # -------------------------------------------------
    ner_preds = run_ner(full_text)

    ner_detections = map_ner_to_tokens(
        ner_preds,
        tokens,
        full_text,
        image_size
    )

    # -------------------------------------------------
    # Pattern Matching
    # -------------------------------------------------
    engine = TokenAlignmentEngine(tokens, image_size)

    pattern_detections = []

    disabled_patterns = []
    disabled_file = MODEL_CACHE_DIR / "disabled_patterns.json"

    if disabled_file.exists():
        disabled_patterns = json.load(open(disabled_file))

    for pattern, label, name, priority in ID_PATTERNS + HEALTH_PATTERNS:
        if name in disabled_patterns:
            continue

        dets = engine.find_pattern_in_tokens(pattern, label, name, priority)
        if dets:
            pattern_detections.extend(dets)

    # -------------------------------------------------
    # Heuristic Detectors
    # -------------------------------------------------
    field_detections = detect_field_values(tokens, image_size)
    cap_detections = detect_capitalized_names(tokens, image_size)
    context_detections = detect_name_field_context(tokens, image_size)
    photo_detections = detect_photos(pil_img)
    qr_detections = detect_qr_codes(pil_img)

    # -------------------------------------------------
    # Combine All
    # -------------------------------------------------
    all_detections = (
        ner_detections +
        pattern_detections +
        field_detections +
        cap_detections +
        context_detections +
        photo_detections +
        qr_detections +
        mrz_detections
    )

    # Deduplicate
    all_detections = engine._deduplicate(all_detections)

    # -------------------------------------------------
    # Validation + Calibration
    # -------------------------------------------------
    validated = []

    for det in all_detections:

        word = det.get("word", "")
        label = det.get("label", "")
        pattern_name = det.get("pattern", "")

        is_valid = True

        # --- Aadhaar checksum
        if label == "B-DOC":
            if pattern_name == "AADHAAR":
                cleaned = word.replace(" ", "").replace("-", "")
                if not validate_aadhaar_checksum(cleaned):
                    is_valid = False

            elif pattern_name == "PAN":
                if not validate_pan_checksum(word):
                    is_valid = False

        if not is_valid:
            continue

        # Confidence calibration
        if "score" in det:
            det["score"] = _CONFIDENCE_CALIBRATOR.calibrate_score(
                label,
                det.get("score", 0.5),
                pattern_name
            )

        validated.append(det)

    # -------------------------------------------------
    # ✅ ML GATING LAYER
    # -------------------------------------------------
    model_path = MODEL_CACHE_DIR / "gating_model.pkl"

    if model_path.exists():

        try:
            clf = joblib.load(model_path)
            gated = []

            for det in validated:
                features = extract_detection_features(det, image_size)
                X = [list(features.values())]

                prob = clf.predict_proba(X)[0][1]

                if prob > 0.5:
                    gated.append(det)

            print(f"[GATING] Reduced {len(validated)} → {len(gated)} detections")
            validated = gated

        except Exception as e:
            print(f"[WARN] Gating model failed: {e}")

    # -------------------------------------------------
    # Record For Training (AFTER GATING)
    # -------------------------------------------------
    if _TRAINING_SYSTEM:
        for det in validated:

            features = extract_detection_features(det, image_size)

            _TRAINING_SYSTEM.record_detection({
                **det,
                "features": features
            }, page_hash)

    # -------------------------------------------------
    # Risk Score
    # -------------------------------------------------
    risk_score = sum(det.get("priority", 0) for det in validated)
    print(f"[RISK] Page risk score: {risk_score}")

    print(f"\n[TOTAL] {len(validated)} detections:")
    for i, d in enumerate(validated, 1):
        print(f"{i:3d}. {d.get('pattern', d.get('label'))} | {d.get('word','')[:35]}")

    # -------------------------------------------------
    # Redaction
    # -------------------------------------------------
    redacted_page = redact_image(
        pil_img,
        validated,
        level=args.redact_level
    )

    return redacted_page, validated

# ==================== PATTERN MATCHING ====================
class TokenAlignmentEngine:
    """Pattern matching engine."""
    
    def __init__(self, tokens: List[Dict], image_size: Tuple[int, int]):
        self.tokens = tokens
        self.image_size = image_size
    
    def find_pattern_in_tokens(self, pattern: re.Pattern, label: str, 
                               pattern_name: str, priority: int) -> List[Dict]:
        """Find patterns with strict validation."""
        detections = []

        for token in self.tokens:
            if MRZ_PATTERN.fullmatch(token["text"]):
                merged_bbox = self._token_to_bbox(token)
                detections.append({
                    "word": token["text"],
                    "bbox": merged_bbox,
                    "label": "B-DOC",
                    "pattern": "MRZ",
            "priority": 100
        })

        
        for token in self.tokens:
            text = token.get("text", "").strip()
            if pattern.fullmatch(text):
                bbox = self._token_to_bbox(token)
                if bbox:
                    detections.append({
                        "word": text,
                        "bbox": bbox,
                        "label": label,
                        "pattern": pattern_name,
                        "priority": priority,
                    })
        
        for window_size in range(2, min(11, len(self.tokens) + 1)):
            for start_idx in range(len(self.tokens) - window_size + 1):
                window_tokens = self.tokens[start_idx:start_idx + window_size]
                
                for join_char in ["", " ", "-"]:
                    combined = join_char.join([t.get("text", "").strip() 
                                              for t in window_tokens])
                    combined_clean = re.sub(r'\s+', ' ', combined).strip()
                    
                    if pattern.fullmatch(combined_clean):
                        bbox = self._merge_bboxes(window_tokens)
                        if bbox:
                            detections.append({
                                "word": combined_clean,
                                "bbox": bbox,
                                "label": label,
                                "pattern": pattern_name,
                                "priority": priority,
                            })
                            break
        
        return self._deduplicate(detections)
    
    def _token_to_bbox(self, token: Dict) -> Optional[List[int]]:
        """Convert token to bbox."""
        x0 = token.get("left", 0)
        y0 = token.get("top", 0)
        w = token.get("width", 0)
        h = token.get("height", 0)
        return validate_bbox([x0, y0, x0 + w, y0 + h], self.image_size)
    
    def _merge_bboxes(self, tokens: List[Dict]) -> Optional[List[int]]:
        """Merge token bboxes."""
        if not tokens:
            return None
        
        valid_bboxes = []
        for t in tokens:
            bbox = self._token_to_bbox(t)
            if bbox:
                valid_bboxes.append(bbox)
        
        if not valid_bboxes:
            return None
        
        x0 = min(b[0] for b in valid_bboxes)
        y0 = min(b[1] for b in valid_bboxes)
        x1 = max(b[2] for b in valid_bboxes)
        y1 = max(b[3] for b in valid_bboxes)
        
        return validate_bbox([x0, y0, x1, y1], self.image_size)
    
    def _deduplicate(self, detections: List[Dict]) -> List[Dict]:
        """
        Improved deduplication:
        - Removes near-duplicates (IoU + text similarity)
        - Merges horizontally adjacent tokens on same line
        - Keeps higher priority detections
        """

        if not detections:
            return []

        # Sort by priority (highest first)
        sorted_dets = sorted(
            detections,
            key=lambda d: d.get("priority", 0),
            reverse=True
        )

        kept = []

        for det in sorted_dets:
            bbox = det.get("bbox")
            word = det.get("word", "").strip().lower()

            if not bbox:
                continue

            x0, y0, x1, y1 = bbox

            is_duplicate = False

            for kept_det in kept:
                kept_bbox = kept_det.get("bbox")
                kept_word = kept_det.get("word", "").strip().lower()

                if not kept_bbox:
                    continue

                kx0, ky0, kx1, ky1 = kept_bbox

                # Compute IoU
                iou = bbox_iou(bbox, kept_bbox)

                # Compute vertical alignment difference
                y_diff = abs(y0 - ky0)

                # Compute horizontal gap
                horizontal_gap = min(abs(x1 - kx0), abs(kx1 - x0))

                # Text similarity
                text_similarity = fuzz.ratio(word, kept_word)

                # -------- CASE 1: Strong overlap duplicate --------
                if iou > 0.6 and text_similarity > 85:
                    is_duplicate = True
                    break

                # -------- CASE 2: Same line + horizontally close (merge) --------
                if y_diff < 15 and horizontal_gap < 20:
                    # Merge bounding boxes
                    merged_bbox = [
                        min(x0, kx0),
                        min(y0, ky0),
                        max(x1, kx1),
                        max(y1, ky1),
                    ]

                    kept_det["bbox"] = merged_bbox
                    kept_det["word"] = kept_word + " " + word
                    is_duplicate = True
                    break

            if not is_duplicate:
                kept.append(det)

        return kept

 
# ==================== FIELD VALUE DETECTION ====================
def detect_field_values(tokens: List[Dict], image_size: Tuple[int, int]) -> List[Dict]:
    """Detect field values with EXPANDED search - bidirectional."""
    detections = []
    
    for i, token in enumerate(tokens):
        text = token.get("text", "").strip()
        if len(text) < 3:
            continue
        
        for pattern, label, name, priority in SENSITIVE_FIELD_PATTERNS:
            if not pattern.search(text):
                continue
            
            value_tokens = []
            label_token = token
            
            for j in range(max(0, i - 10), i):
                prev_token = tokens[j]
                prev_text = prev_token.get("text", "").strip()
                
                if not prev_text or prev_text in [':', '-', '/', '|', '.']:
                    continue
                
                label_top = label_token.get("top", 0)
                label_height = label_token.get("height", 20)
                prev_top = prev_token.get("top", 0)
                
                if abs(prev_top - label_top) <= max(15, label_height * 0.7):
                    if (prev_text[0].isupper() and 
                        prev_text.isalpha() and 
                        not is_non_sensitive_text(prev_text) and
                        len(prev_text) >= 3):
                        value_tokens.insert(0, prev_token)
            
            for j in range(i + 1, min(i + 15, len(tokens))):
                next_token = tokens[j]
                next_text = next_token.get("text", "").strip()
                
                if next_text in [':', '-', '/', '|', '', '.']:
                    continue
                
                if any(p[0].search(next_text) for p in SENSITIVE_FIELD_PATTERNS):
                    break
                
                label_top = label_token.get("top", 0)
                label_height = label_token.get("height", 20)
                next_top = next_token.get("top", 0)
                
                if abs(next_top - label_top) <= max(15, label_height * 0.7):
                    if not is_non_sensitive_text(next_text):
                        value_tokens.append(next_token)
                    
                    if 'NAME' in name and len(value_tokens) >= 8:
                        break
                    elif len(value_tokens) >= 3:
                        break
                else:
                    break
            
            if value_tokens:
                xs = [t["left"] for t in value_tokens]
                ys = [t["top"] for t in value_tokens]
                x2s = [t["left"] + t["width"] for t in value_tokens]
                y2s = [t["top"] + t["height"] for t in value_tokens]
                
                bbox = validate_bbox([min(xs), min(ys), max(x2s), max(y2s)], image_size)
                if bbox:
                    value_text = " ".join([t.get("text", "") for t in value_tokens])
                    if len(value_text.strip()) >= 3:
                        detections.append({
                            "word": value_text,
                            "bbox": bbox,
                            "label": label,
                            "pattern": name,
                            "priority": priority,
                        })
    
    return detections
def main():
    """Enhanced main with proper feedback + multi-page support."""
    global _PRIVACY_MANAGER, _TRAINING_SYSTEM

    parser = argparse.ArgumentParser(
        description="Enhanced PDF Redactor with Self-Training & Privacy"
    )

    parser.add_argument("--input", "-i", help="Input PDF")
    parser.add_argument(
        "--redact-level", "-rl",
        type=int,
        default=2,
        choices=[1, 2, 3, 4],
        help="Redaction level"
    )
    parser.add_argument("--lang", default="eng")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--dpi", type=int, default=PDF_DPI)
    parser.add_argument("--train", action="store_true")
    parser.add_argument("--no-privacy", action="store_true")
    parser.add_argument("--interactive", action="store_true")

    args = parser.parse_args()

    # -------------------------------------------------
    # Privacy Setup
    # -------------------------------------------------
    privacy_config = PRIVACY_CONFIG.copy()

    if args.no_privacy:
        privacy_config["auto_delete_training_data"] = False
        privacy_config["anonymize_feedback"] = False
        privacy_config["use_differential_privacy"] = False

    _PRIVACY_MANAGER = PrivacyManager(privacy_config)
    _TRAINING_SYSTEM = SelfTrainingSystem(_PRIVACY_MANAGER)

    _PRIVACY_MANAGER.cleanup_old_training_data()

    # -------------------------------------------------
    # Training-only mode
    # -------------------------------------------------
    if args.train:
        print("=" * 70)
        print("TRAINING MODE")
        print("=" * 70)
        _TRAINING_SYSTEM.train_from_feedback()
        _PRIVACY_MANAGER.cleanup_session()
        return

    if not args.input:
        print("[ERROR] --input required")
        return

    print("=" * 70)
    print("ENHANCED PDF REDACTOR WITH SELF-TRAINING")
    print("=" * 70)

    # -------------------------------------------------
    # Load PDF
    # -------------------------------------------------
    try:
        pil_pages = pdf_to_images(args.input, dpi=args.dpi)
        print(f"[PDF] Loaded {len(pil_pages)} page(s)")
    except Exception as e:
        print(f"[ERROR] Failed to load PDF: {e}")
        return

    redacted_images = []
    all_pages_detections = []

    # -------------------------------------------------
    # Process Pages
    # -------------------------------------------------
    for page_no, pil_img in enumerate(pil_pages, 1):
        redacted_page, detections = process_page(pil_img, page_no, args)
        redacted_images.append(redacted_page)
        all_pages_detections.append(detections)

    # -------------------------------------------------
    # Save PDF
    # -------------------------------------------------
    out_pdf = OUTPUTS_DIR / f"redacted_{now_ts()}.pdf"

    if len(redacted_images) == 1:
        redacted_images[0].save(out_pdf, "PDF")
    else:
        redacted_images[0].save(
            out_pdf,
            save_all=True,
            append_images=redacted_images[1:]
        )

    print(f"[SUCCESS] Saved: {out_pdf}")

    # -------------------------------------------------
    # Generate Report
    # -------------------------------------------------
    report_path = OUTPUTS_DIR / f"report_{now_ts()}.txt"
    generate_report(all_pages_detections, report_path)

    # -------------------------------------------------
    # GLOBAL FEEDBACK MODE (FIXED)
    # -------------------------------------------------
    total = sum(len(d) for d in all_pages_detections)

    print("=" * 70)
    print(f"COMPLETE: {total} detections across {len(all_pages_detections)} page(s)")

    if args.interactive and total > 0:

        print("\n=== FEEDBACK MODE ===")

        # Build global detection list
        global_detections = []
        counter = 1

        for page_idx, page_dets in enumerate(all_pages_detections, start=1):
            for det in page_dets:
                global_detections.append({
                    "page": page_idx,
                    "det": det
                })

                word = det.get("word", "")[:40]
                pattern = det.get("pattern", det.get("label", "UNKNOWN"))

                print(f"{counter:3d}. (P{page_idx}) {pattern:20s} | {word}")
                counter += 1

        # -----------------------------------
        # Incorrect detections
        # -----------------------------------
        wrong_input = input(
            "\nEnter WRONG detection numbers (comma separated), or press Enter if all correct:\n> "
        ).strip()

        wrong_indices = set()

        if wrong_input:
            for val in wrong_input.split(","):
                val = val.strip()
                if val.isdigit():
                    wrong_indices.add(int(val))

        # -----------------------------------
        # Record feedback
        # -----------------------------------
        for idx, item in enumerate(global_detections, start=1):
            is_correct = idx not in wrong_indices

            _TRAINING_SYSTEM.add_user_feedback(
                detection_index=idx - 1,
                is_correct=is_correct
            )

        print(f"[FEEDBACK] Recorded {len(wrong_indices)} incorrect detections.")

        # -----------------------------------
        # Missed detections
        # -----------------------------------
        missed_input = input(
            "\nEnter MISSED sensitive words (comma separated), or press Enter if none:\n> "
        ).strip()

        if missed_input:
            missed_words = [
                w.strip() for w in missed_input.split(",") if w.strip()
            ]

            for word in missed_words:
                _TRAINING_SYSTEM.feedback_buffer.append({
                    "label": "B-SENSITIVE",
                    "pattern": "MISSED_ENTITY",
                    "missed_detection": True,
                    "word": word
                })

            print(f"[FEEDBACK] Recorded {len(missed_words)} missed detections.")

    # -------------------------------------------------
    # Save Training Data AFTER Feedback
    # -------------------------------------------------
    if _TRAINING_SYSTEM:
        _TRAINING_SYSTEM.save_training_batch()

    print("=" * 70)
    print(f"Output PDF: {out_pdf}")
    print(f"Report: {report_path}")

    if not args.no_privacy:
        print(f"[PRIVACY] Session ID: {_PRIVACY_MANAGER.session_id}")

    # -------------------------------------------------
    # Cleanup
    # -------------------------------------------------
    _PRIVACY_MANAGER.cleanup_session()

if __name__ == "__main__":
    main()