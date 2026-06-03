import re
import cv2
import easyocr
from utils.logger import get_logger

logger = get_logger(__name__)

# PII regex patterns
PII_PATTERNS = {
    "PHONE_NUMBER": [
        r"\b(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
        r"\b\d{10}\b",
        r"\b\d{5}[-.\s]?\d{5}\b"
    ],
    "EMAIL_ADDRESS": [
        r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
    ],
    "ID_NUMBER": [
        r"\b[A-Z]{1,2}\d{6,9}\b",  # Passport-like
        r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}\b",  # Aadhaar-like
    ],
    "PERSON_NAME": [
        r"\b(Mr\.|Mrs\.|Dr\.|Ms\.)\s[A-Z][a-z]+(?: [A-Z][a-z]+)?\b"
    ],
    "LOCATION": [
        r"\b\d{1,4}[,\s]+[A-Za-z\s]+(Street|St|Avenue|Ave|Road|Rd|Lane|Blvd|Nagar|Colony)\b"
    ],
    "VEHICLE_PLATE": [
        r"\b[A-Z]{2}[-\s]?\d{2}[-\s]?[A-Z]{1,2}[-\s]?\d{4}\b"  # Indian plate format
    ]
}

class OCREngine:
    def __init__(self):
        logger.info("Loading EasyOCR engine (this may take a moment)...")
        self.reader = easyocr.Reader(['en'], gpu=False, verbose=False)
        logger.info("EasyOCR engine ready. PII detection via regex patterns.")

    def extract_text(self, frame, box):
        """
        Crop the frame at the given box and run EasyOCR.
        Returns extracted text string.
        """
        x1, y1, x2, y2 = [max(0, int(v)) for v in box]
        h, w = frame.shape[:2]
        x2 = min(x2, w)
        y2 = min(y2, h)

        if x2 <= x1 or y2 <= y1:
            return ""

        roi = frame[y1:y2, x1:x2]
        try:
            results = self.reader.readtext(roi, detail=0)
            return " ".join(results).strip()
        except Exception as e:
            logger.warning(f"OCR error: {e}")
            return ""

    def is_sensitive(self, text):
        """
        Checks extracted text against PII regex patterns.
        Returns (is_pii: bool, detected_entity_type: str | None)
        """
        if not text:
            return False, None
        for entity_type, patterns in PII_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    logger.info(f"PII detected: [{entity_type}] in text: '{text}'")
                    return True, entity_type
        return False, None

    def analyze_regions(self, frame, regions):
        """
        For each text region: run OCR then check for PII.
        Returns only regions that contain PII - ready for redaction.
        """
        pii_regions = []
        for region in regions:
            text = self.extract_text(frame, region["box"])
            if not text:
                continue
            is_pii, entity_type = self.is_sensitive(text)
            if is_pii:
                region["text"] = text
                region["entity_type"] = entity_type
                pii_regions.append(region)
        return pii_regions
