class PrivacyRiskCalculator:
    def __init__(self):
        self.points_map = {
            "face": 2,
            "plate": 3,
            "phone_number": 4,
            "address": 5,
            "email_address": 3,
            "person_name": 4,
            "id_number": 5
        }
        self.max_score = 50

    def calculate_frame_score(self, detections):
        """
        Calculates the privacy risk score for a single frame based on detections.
        detections should be a list of dicts like:
        [{"type": "face"}, {"type": "phone_number"}, ...]
        """
        score = 0
        for det in detections:
            entity_type = det.get("type", "").lower()
            score += self.points_map.get(entity_type, 1) # Default 1 point for unknown

        return min(score, self.max_score)

    def calculate_total_score(self, all_detections):
        """
        Calculates a global risk score for the video.
        """
        return self.calculate_frame_score(all_detections)
