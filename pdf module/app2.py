import os
import re
import json
import time
import hashlib
import argparse
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from collections import defaultdict
from datetime import datetime, timedelta
import tempfile
import shutil
 
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps
import cv2
from pdf2image import convert_from_path
import pytesseract
from pytesseract import Output
import torch
from transformers import pipeline
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
    "xlm-roberta-large-finetuned-conll03-english",
    "Davlan/distilbert-base-multilingual-cased-ner-hrl"
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
]
 
SENSITIVE_FIELD_PATTERNS = [
    (re.compile(r"^(name|नाम)$", re.IGNORECASE), "B-PER", "NAME_FIELD", 95),
    (re.compile(r"(father'?s?\s+name|पिता\s*का\s*नाम)", re.IGNORECASE), "B-PER", "FATHER_NAME", 95),
    (re.compile(r"(mother'?s?\s+name|माता\s*का\s*नाम)", re.IGNORECASE), "B-PER", "MOTHER_NAME", 95),
    (re.compile(r"(date\s+of\s+birth|dob|जन्म\s*तिथि)", re.IGNORECASE), "B-DATE", "DOB_FIELD", 90),
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
    """Implements privacy-preserving self-training."""
    
    def __init__(self, privacy_manager: PrivacyManager):
        self.privacy_manager = privacy_manager
        self.feedback_buffer = []
    
    def record_detection(self, detection: Dict, page_hash: str):
        """Record a detection for potential training."""
        anonymized = {
            "page_hash": page_hash,
            "label": detection.get("label"),
            "pattern": detection.get("pattern"),
            "score": detection.get("score", 0.0),
            "bbox_size": (
                detection.get("bbox", [0, 0, 0, 0])[2] - detection.get("bbox", [0, 0, 0, 0])[0],
                detection.get("bbox", [0, 0, 0, 0])[3] - detection.get("bbox", [0, 0, 0, 0])[1]
            ),
            "timestamp": time.time(),
            "session_id": self.privacy_manager.session_id
        }
        
        self.feedback_buffer.append(anonymized)
    
    def add_user_feedback(self, detection_index: int, is_correct: bool, correction: Optional[str] = None):
        """Add user feedback for a detection."""
        if 0 <= detection_index < len(self.feedback_buffer):
            self.feedback_buffer[detection_index].update({
                "user_feedback": is_correct,
                "correction": correction,
                "feedback_time": time.time()
            })
            
            det = self.feedback_buffer[detection_index]
            if _CONFIDENCE_CALIBRATOR:
                _CONFIDENCE_CALIBRATOR.record_feedback(
                    det['label'], 
                    det['pattern'], 
                    det['score'], 
                    is_correct
                )
    
    def save_training_batch(self):
        """Save accumulated feedback for training."""
        if not self.feedback_buffer:
            return
        
        privacy_buffer = self.privacy_manager.apply_differential_privacy(self.feedback_buffer.copy())
        
        timestamp = int(time.time())
        filename = FEEDBACK_DIR / f"feedback_{timestamp}.json"
        
        try:
            with open(filename, 'w') as f:
                json.dump(privacy_buffer, f, indent=2)
            print(f"[TRAINING] Saved {len(privacy_buffer)} feedback samples to {filename}")
            
            self.privacy_manager.register_temp_file(filename)
            
        except Exception as e:
            print(f"[ERROR] Failed to save training data: {e}")
        
        self.feedback_buffer.clear()
    
    def train_from_feedback(self):
        """Train/update models from accumulated feedback."""
        feedback_files = list(FEEDBACK_DIR.glob("feedback_*.json"))
        
        if not feedback_files:
            print("[TRAINING] No feedback data available")
            return
        
        print(f"[TRAINING] Processing {len(feedback_files)} feedback files...")
        
        label_improvements = defaultdict(lambda: {"correct": 0, "total": 0})
        pattern_improvements = defaultdict(lambda: {"correct": 0, "total": 0})
        
        for feedback_file in feedback_files:
            try:
                with open(feedback_file, 'r') as f:
                    data = json.load(f)
                
                for item in data:
                    if "user_feedback" in item:
                        label = item.get("label", "UNKNOWN")
                        pattern = item.get("pattern", "UNKNOWN")
                        is_correct = item["user_feedback"]
                        
                        label_improvements[label]["total"] += 1
                        pattern_improvements[pattern]["total"] += 1
                        
                        if is_correct:
                            label_improvements[label]["correct"] += 1
                            pattern_improvements[pattern]["correct"] += 1
                
            except Exception as e:
                print(f"[WARN] Failed to process {feedback_file}: {e}")
        
        print("\n[TRAINING] Feedback Statistics:")
        print("=" * 70)
        print("\nLabel Performance:")
        for label, stats in sorted(label_improvements.items()):
            accuracy = stats["correct"] / stats["total"] if stats["total"] > 0 else 0
            print(f"  {label:15s}: {accuracy:.1%} ({stats['correct']}/{stats['total']})")
        
        print("\nPattern Performance:")
        for pattern, stats in sorted(pattern_improvements.items()):
            accuracy = stats["correct"] / stats["total"] if stats["total"] > 0 else 0
            print(f"  {pattern:20s}: {accuracy:.1%} ({stats['correct']}/{stats['total']})")
        
        print("\n[TRAINING] Confidence calibration updated from feedback")
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
                device=device,
                model_kwargs={"max_length": 512, "truncation": True}
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
    """Run ALL configured NER models."""
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
    
    print(f"[NER] Total predictions from all models: {len(all_preds)}")
    return all_preds
 
def map_ner_to_tokens(ner_preds: List[Dict], tokens: List[Dict], 
                      full_text: str, image_size: Tuple[int, int]) -> List[Dict]:
    """Map NER predictions to OCR tokens with filtering."""
    detections = []
    token_texts = [t["text"] for t in tokens]
    joined = " ".join(token_texts).lower()
    
    for pred in ner_preds:
        word = pred.get("word", "").strip()
        if not word or len(word) <= 2:
            continue
        
        if is_non_sensitive_text(word):
            continue
        
        label = canonicalize_label(pred.get("entity_group", pred.get("entity", "O")))
        if label == "O":
            continue
        
        score = pred.get("score", 0.0)
        
        if label == "B-PER":
            if score < 0.45:
                continue
        else:
            if score < 0.70:
                continue
        
        word_lower = word.lower()
        if word_lower in joined:
            idx = joined.find(word_lower)
            cum = 0
            start_idx = None
            end_idx = None
            
            for i, t in enumerate(token_texts):
                t_low = t.lower()
                if start_idx is None and cum + len(t_low) > idx:
                    start_idx = i
                if start_idx is not None:
                    if cum + len(" ".join(token_texts[start_idx:i + 1]).lower()) >= idx + len(word_lower):
                        end_idx = i
                        break
                cum += len(t_low) + 1
            
            if start_idx is not None and end_idx is not None:
                xs = [tokens[j]["left"] for j in range(start_idx, end_idx + 1)]
                ys = [tokens[j]["top"] for j in range(start_idx, end_idx + 1)]
                x2s = [tokens[j]["left"] + tokens[j]["width"] for j in range(start_idx, end_idx + 1)]
                y2s = [tokens[j]["top"] + tokens[j]["height"] for j in range(start_idx, end_idx + 1)]
                
                bbox = validate_bbox([min(xs), min(ys), max(x2s), max(y2s)], image_size)
                if bbox:
                    detections.append({
                        "word": " ".join(token_texts[start_idx:end_idx + 1]),
                        "bbox": bbox,
                        "label": label,
                        "score": score,
                        "priority": 75
                    })
    
    return detections
 
def detect_capitalized_names(tokens: List[Dict], image_size: Tuple[int, int]) -> List[Dict]:
    """Detect capitalized name sequences."""
    detections = []
    
    i = 0
    while i < len(tokens):
        token = tokens[i]
        text = token.get("text", "").strip()
        
        if text.lower() in IGNORE_WORDS:
            i += 1
            continue
        
        is_name_candidate = (
            len(text) >= 3 and
            text[0].isupper() and
            sum(c.isalpha() for c in text) >= len(text) * 0.7 and
            not is_non_sensitive_text(text)
        )
        
        if is_name_candidate:
            name_tokens = [token]
            curr_top = token.get("top", 0)
            curr_height = token.get("height", 20)
            
            for j in range(i + 1, min(i + 6, len(tokens))):
                next_token = tokens[j]
                next_text = next_token.get("text", "").strip()
                next_top = next_token.get("top", 0)
                
                if next_text.lower() in IGNORE_WORDS:
                    break
                
                if abs(next_top - curr_top) <= max(15, curr_height * 0.7):
                    is_next_name = (
                        len(next_text) >= 2 and
                        next_text[0].isupper() and
                        sum(c.isalpha() for c in next_text) >= len(next_text) * 0.7 and
                        not is_non_sensitive_text(next_text)
                    )
                    
                    if is_next_name:
                        name_tokens.append(next_token)
                    else:
                        break
                else:
                    break
            
            if len(name_tokens) >= 1:
                full_name = " ".join([t.get("text", "") for t in name_tokens])
                if not is_non_sensitive_text(full_name) and len(full_name) >= 4:
                    xs = [t["left"] for t in name_tokens]
                    ys = [t["top"] for t in name_tokens]
                    x2s = [t["left"] + t["width"] for t in name_tokens]
                    y2s = [t["top"] + t["height"] for t in name_tokens]
                    
                    bbox = validate_bbox([min(xs), min(ys), max(x2s), max(y2s)], image_size)
                    if bbox:
                        priority = 85 if len(name_tokens) >= 2 else 82
                        detections.append({
                            "word": full_name,
                            "bbox": bbox,
                            "label": "B-PER",
                            "pattern": "CAPITALIZED_NAME",
                            "priority": priority,
                        })
                
                i += len(name_tokens)
                continue
        
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
def redact_image(pil_img: Image.Image, detections: List[Dict], mode: str = "mask") -> Image.Image:
    """Apply redaction."""
    img = pil_img.copy().convert("RGB")
    draw = ImageDraw.Draw(img)
    
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
    except:
        font = ImageFont.load_default()
    
    image_size = (img.width, img.height)
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
        
        if mode == "mask":
            draw.rectangle([x0, y0, x1, y1], fill=(0, 0, 0))
            redacted_count += 1
        elif mode == "synth":
            draw.rectangle([x0, y0, x1, y1], fill=(255, 255, 255), outline=(200, 200, 200))
            synth_text = "█" * min(8, (x1 - x0) // 8)
            draw.text((x0 + 2, y0 + 2), synth_text, fill=(0, 0, 0), font=font)
            redacted_count += 1
    
    print(f"[REDACT] Applied {redacted_count} redactions")
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
def process_page(pil_img: Image.Image, page_no: int, args) -> Tuple[Image.Image, List[Dict]]:
    """Process a single page with rotation detection and self-training."""
    global _CONFIDENCE_CALIBRATOR, _TRAINING_SYSTEM
    
    if _CONFIDENCE_CALIBRATOR is None:
        _CONFIDENCE_CALIBRATOR = ConfidenceCalibrator()
    
    print(f"\n{'='*70}")
    print(f"PAGE {page_no}")
    print(f"{'='*70}")
    print(f"Size: {pil_img.width}x{pil_img.height}")
    
    # Generate page hash for training
    page_hash = hashlib.md5(pil_img.tobytes()).hexdigest()[:16]
    
    # Detect and fix orientation
    pil_img, rotation = detect_and_fix_orientation(pil_img)
    if rotation != 0:
        print(f"[INFO] Applied {rotation}° rotation correction")
        print(f"[INFO] New size: {pil_img.width}x{pil_img.height}")
    
    # Multi-engine OCR
    full_text, tokens = ocr_multi_engine(pil_img, lang=args.lang)
    print(f"[INFO] Total tokens: {len(tokens)}")
    
    if full_text:
        preview = full_text[:200].replace('\n', ' ')
        print(f"[INFO] Text preview: {preview}...")
    
    if not tokens:
        print("[WARN] No text detected - trying visual detection only")
        photo_detections = detect_photos(pil_img)
        qr_detections = detect_qr_codes(pil_img)
        all_detections = photo_detections + qr_detections
        
        if all_detections:
            print(f"[VISUAL] Found {len(all_detections)} visual elements")
            if args.debug:
                debug_path = OUTPUTS_DIR / f"debug_page_{page_no}.png"
                save_debug_visualization(pil_img, all_detections, debug_path)
            redacted_page = redact_image(pil_img, all_detections, mode=args.redact_mode)
            return redacted_page, all_detections
        
        print("[WARN] No detections possible on this page")
        return pil_img, []
    
    # NER
    ner_preds = run_ner(full_text)
    ner_detections = map_ner_to_tokens(ner_preds, tokens, full_text, 
                                      (pil_img.width, pil_img.height))
    print(f"[NER] {len(ner_detections)} detections")
    
    # Pattern matching
    print("[PATTERN] Searching...")
    engine = TokenAlignmentEngine(tokens, (pil_img.width, pil_img.height))
    pattern_detections = []
    
    for pattern, label, name, priority in ID_PATTERNS:
        dets = engine.find_pattern_in_tokens(pattern, label, name, priority)
        if dets:
            pattern_detections.extend(dets)
    
    print(f"[PATTERN] {len(pattern_detections)} detections")
    
    # Field values
    field_detections = detect_field_values(tokens, (pil_img.width, pil_img.height))
    print(f"[FIELD] {len(field_detections)} detections")
    
    # Capitalized names
    cap_detections = detect_capitalized_names(tokens, (pil_img.width, pil_img.height))
    print(f"[NAME] {len(cap_detections)} detections")
    
    # Name field context
    context_detections = detect_name_field_context(tokens, (pil_img.width, pil_img.height))
    print(f"[CONTEXT] {len(context_detections)} detections")
    
    # Photos
    photo_detections = detect_photos(pil_img)
    
    # QR codes
    qr_detections = detect_qr_codes(pil_img)
    
    # Combine all
    all_detections = (
        ner_detections + 
        pattern_detections + 
        field_detections + 
        cap_detections +
        context_detections +
        photo_detections + 
        qr_detections
    )
    
    # Final deduplication
    all_detections = engine._deduplicate(all_detections)
    
    # Validate and calibrate detections
    print(f"\n[VALIDATION] Validating {len(all_detections)} detections...")
    validated_detections = []
    
    for det in all_detections:
        word = det.get("word", "")
        label = det.get("label", "")
        pattern_name = det.get("pattern", "")
        
        # Apply checksum validation
        is_valid = True
        if label == "B-DOC":
            if pattern_name == "AADHAAR":
                cleaned = word.replace(" ", "").replace("-", "")
                if not validate_aadhaar_checksum(cleaned):
                    print(f"[VALIDATION] ✗ Invalid Aadhaar checksum: {word}")
                    is_valid = False
            elif pattern_name == "PAN":
                if not validate_pan_checksum(word):
                    print(f"[VALIDATION] ✗ Invalid PAN format: {word}")
                    is_valid = False
        
        if not is_valid:
            continue
        
        # Apply confidence calibration
        if "score" in det:
            original_score = det["score"]
            det["score"] = _CONFIDENCE_CALIBRATOR.calibrate_score(
                label, 
                original_score,
                pattern_name
            )
            
            if abs(det["score"] - original_score) > 0.1:
                print(f"[CALIB] Adjusted {label} score: {original_score:.2f} → {det['score']:.2f}")
        
        validated_detections.append(det)
        
        # Record for training
        if _TRAINING_SYSTEM:
            _TRAINING_SYSTEM.record_detection(det, page_hash)
    
    print(f"\n[TOTAL] {len(validated_detections)} final validated detections:")
    for i, d in enumerate(validated_detections, 1):
        word = d.get('word', '')[:35]
        pattern = d.get('pattern', d.get('label', 'UNKNOWN'))
        priority = d.get('priority', 0)
        score = d.get('score', 0)
        print(f"  {i:2d}. [{priority:2d}|{score:.2f}] {pattern:20s} | {word}")
    
    # Debug visualization
    if args.debug:
        debug_path = OUTPUTS_DIR / f"debug_page_{page_no}.png"
        save_debug_visualization(pil_img, validated_detections, debug_path)
    
    # Redact
    redacted_page = redact_image(pil_img, validated_detections, mode=args.redact_mode)
    
    return redacted_page, validated_detections
 
def main():
    """Enhanced main with self-training and privacy management."""
    global _PRIVACY_MANAGER, _TRAINING_SYSTEM
    
    parser = argparse.ArgumentParser(description="Enhanced PDF Redactor with Self-Training & Privacy")
    parser.add_argument("--input", "-i", required=True, help="Input PDF")
    parser.add_argument("--redact-mode", "-r", default="mask", 
                       choices=["mask", "synth"], help="Redaction mode")
    parser.add_argument("--lang", default="eng", help="OCR language")
    parser.add_argument("--debug", action="store_true", help="Debug mode")
    parser.add_argument("--dpi", type=int, default=PDF_DPI, help="PDF DPI")
    parser.add_argument("--train", action="store_true",
                       help="Train from accumulated feedback")
    parser.add_argument("--no-privacy", action="store_true",
                       help="Disable privacy features (NOT RECOMMENDED)")
    
    args = parser.parse_args()
    
    # Initialize privacy manager
    privacy_config = PRIVACY_CONFIG.copy()
    if args.no_privacy:
        print("[WARN] Privacy features disabled!")
        privacy_config["auto_delete_training_data"] = False
        privacy_config["anonymize_feedback"] = False
        privacy_config["use_differential_privacy"] = False
    
    _PRIVACY_MANAGER = PrivacyManager(privacy_config)
    _TRAINING_SYSTEM = SelfTrainingSystem(_PRIVACY_MANAGER)
    
    # Cleanup old training data
    _PRIVACY_MANAGER.cleanup_old_training_data()
    
    # If train mode, just train and exit
    if args.train:
        print("=" * 70)
        print("TRAINING MODE")
        print("=" * 70)
        _TRAINING_SYSTEM.train_from_feedback()
        _PRIVACY_MANAGER.cleanup_session()
        return
    
    print("=" * 70)
    print("ENHANCED PDF REDACTOR WITH SELF-TRAINING")
    print("=" * 70)
    print(f"Input: {args.input}")
    print(f"Mode: {args.redact_mode}")
    print(f"DPI: {args.dpi}")
    print(f"Language: {args.lang}")
    print(f"Debug: {args.debug}")
    print(f"\nPrivacy: {'ENABLED' if not args.no_privacy else 'DISABLED'}")
    
    if not args.no_privacy:
        print("\nPrivacy Features:")
        print(f"  ✓ Automatic data deletion: {privacy_config['auto_delete_training_data']}")
        print(f"  ✓ Retention period: {privacy_config['retention_days']} days")
        print(f"  ✓ Differential privacy: {privacy_config['use_differential_privacy']} (ε={privacy_config['privacy_epsilon']})")
        print(f"  ✓ Anonymization: {privacy_config['anonymize_feedback']}")
    
    print("\nConfiguration:")
    print(f"  OCR Engines: {len(OCR_ENGINES)}")
    for i, engine in enumerate(OCR_ENGINES, 1):
        print(f"    {i}. {engine}")
    print(f"  NER Models: {len(AI_MODELS)}")
    for i, model in enumerate(AI_MODELS, 1):
        print(f"    {i}. {model}")
    
    print("\nKEY FEATURES:")
    print("  ✓ Auto rotation detection & correction")
    print("  ✓ Multi-engine OCR (Tesseract + EasyOCR)")
    print("  ✓ Ensemble NER with 3 models")
    print("  ✓ Checksum validation (Aadhaar Verhoeff, PAN)")
    print("  ✓ Confidence calibration & self-training")
    print("  ✓ Bidirectional field value search")
    print("  ✓ Context-aware name detection")
    print("  ✓ Privacy-preserving learning")
    print("  ✓ Automatic old data cleanup")
    print("=" * 70)
    
    try:
        # Convert PDF
        try:
            pil_pages = pdf_to_images(args.input, dpi=args.dpi)
            print(f"\n[PDF] Loaded {len(pil_pages)} page(s)")
        except Exception as e:
            print(f"[ERROR] Failed to load PDF: {e}")
            return
        
        # Process pages
        redacted_images = []
        all_pages_detections = []
        
        for page_no, pil_img in enumerate(pil_pages, 1):
            redacted_page, detections = process_page(pil_img, page_no, args)
            redacted_images.append(redacted_page)
            all_pages_detections.append(detections)
        
        # Save output
        out_pdf = OUTPUTS_DIR / f"redacted_{now_ts()}.pdf"
        print(f"\n[SAVE] Creating PDF...")
        
        if len(redacted_images) == 1:
            redacted_images[0].save(out_pdf, "PDF")
        else:
            redacted_images[0].save(out_pdf, save_all=True, append_images=redacted_images[1:])
        
        print(f"[SUCCESS] Saved: {out_pdf}")
        
        # Generate report
        report_path = OUTPUTS_DIR / f"report_{now_ts()}.txt"
        generate_report(all_pages_detections, report_path)
        
        # Save training data
        if _TRAINING_SYSTEM:
            _TRAINING_SYSTEM.save_training_batch()
        
        # Summary
        total = sum(len(d) for d in all_pages_detections)
        print(f"\n{'='*70}")
        print(f"COMPLETE: {total} redactions across {len(all_pages_detections)} page(s)")
        print(f"{'='*70}")
        print(f"Output PDF: {out_pdf}")
        print(f"Report: {report_path}")
        
        if _TRAINING_SYSTEM and len(_TRAINING_SYSTEM.feedback_buffer) > 0:
            print(f"\n[TRAINING] Collected {len(_TRAINING_SYSTEM.feedback_buffer)} feedback samples")
            print("To improve accuracy:")
            print("  1. Review the redacted PDF")
            print("  2. Provide feedback on any missed/incorrect detections")
            print("  3. Run with --train to update the models")
            print(f"\nFeedback data saved in: {FEEDBACK_DIR}")
        
        # Privacy info
        if not args.no_privacy:
            print(f"\n[PRIVACY] Session ID: {_PRIVACY_MANAGER.session_id}")
            print(f"[PRIVACY] Training data will auto-delete after {privacy_config['retention_days']} days")
        
    except KeyboardInterrupt:
        print("\n\n[INTERRUPTED] Processing cancelled by user")
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Always cleanup
        if _PRIVACY_MANAGER:
            print("\n[PRIVACY] Cleaning up session data...")
            _PRIVACY_MANAGER.cleanup_session()
            print("[PRIVACY] Session cleanup complete")
 
if __name__ == "__main__":
    main()
 
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
        """Remove overlapping detections - STRICT."""
        if not detections:
            return []
        
        sorted_dets = sorted(detections, key=lambda d: d.get("priority", 0), reverse=True)
        kept = []
        
        for det in sorted_dets:
            bbox = det.get("bbox")
            word = det.get("word", "").strip().lower()
            if not bbox:
                continue
            
            is_duplicate = False
            for kept_det in kept:
                kept_bbox = kept_det.get("bbox")
                kept_word = kept_det.get("word", "").strip().lower()
                
                if kept_bbox:
                    iou = bbox_iou(bbox, kept_bbox)
                    text_similarity = fuzz.ratio(word, kept_word)
                    
                    if iou > 0.85 and text_similarity > 90:
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