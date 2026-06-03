import os
from pathlib import Path

# Base Directory Paths
BASE_DIR = Path(__file__).resolve().parent.parent
MODELS_DIR = BASE_DIR / "models_weights"  # Where we would store local PyTorch weights
REPORTS_DIR = BASE_DIR / "reports"
FEEDBACK_DIR = BASE_DIR / "feedback_dataset"

os.makedirs(REPORTS_DIR, exist_ok=True)
os.makedirs(FEEDBACK_DIR, exist_ok=True)

# Detection & Tracking Settings
TRACKING_INTERVAL = 5  # Run full detection every 5 frames, use DeepSORT in between
CONFIDENCE_THRESHOLD_FACE = 0.55
CONFIDENCE_THRESHOLD_PLATE = 0.5

# Ensemble Detection Config
# MTCNNFallback is currently disabled (always returns []), so FaceDetector is
# the only active detector and can never produce more than 1 vote.  Keep this
# at 1 until a second real detector is wired in.
ENSEMBLE_MIN_VOTES = 1  # Minimum votes from ensemble detectors to confirm a face

# Policy Settings
class RedactionMode:
    FACE_ONLY = 1
    PLATE_PII = 2
    FACE_PLATE_PII = 3
    IDENTITY_PROTECT = 4

    # Named modes for the policy engine
    SOCIAL_MEDIA = "social_media"
    LEGAL = "legal"
    SURVEILLANCE = "surveillance"

# Pre-configured Policies
POLICIES = {
    RedactionMode.SOCIAL_MEDIA: {
        "redact_faces": True,
        "redact_plates": True,
        "redact_pii": False,
        "keep_authorized": False
    },
    RedactionMode.LEGAL: {
        "redact_faces": True,
        "redact_plates": True,
        "redact_pii": True,
        "keep_authorized": False
    },
    RedactionMode.SURVEILLANCE: {
        "redact_faces": True,  # Will interact with identity protection
        "redact_plates": False,
        "redact_pii": False,
        "keep_authorized": True
    }
}
