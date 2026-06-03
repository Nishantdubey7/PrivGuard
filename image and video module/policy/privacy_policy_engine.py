from config.settings import POLICIES, RedactionMode
from utils.logger import get_logger

logger = get_logger(__name__)

class PrivacyPolicyEngine:
    def __init__(self, mode=RedactionMode.FACE_PLATE_PII):
        self._set_mode(mode)

    def _set_mode(self, mode):
        self.mode = mode
        if mode in POLICIES:
            self.policy = POLICIES[mode]
            logger.info(f"Loaded strict policy from settings: {self.policy}")
        else:
            # Fallback mapper for numeric modes
            self.policy = {
                "redact_faces": mode in [1, 3, 4],
                "redact_plates": mode in [2, 3],
                "redact_pii": mode in [2, 3],
                "keep_authorized": mode == 4
            }
            logger.info(f"Loaded calculated policy for mode {mode}: {self.policy}")

    def should_redact_face(self, is_authorized=False):
        if not self.policy["redact_faces"]:
            return False
        if self.policy["keep_authorized"] and is_authorized:
            return False
        return True

    def should_redact_plate(self):
        return self.policy["redact_plates"]

    def should_redact_pii(self):
        return self.policy["redact_pii"]
