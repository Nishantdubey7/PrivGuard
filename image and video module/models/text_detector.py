import cv2
from utils.logger import get_logger

logger = get_logger(__name__)

class TextDetector:
    """
    Real text detector using OpenCV's EAST (Efficient and Accurate Scene Text detector).
    EAST is a deep-learning scene text detector built into OpenCV DNN module.
    Falls back to adaptive thresholding if EAST model is not available.
    """

    EAST_MODEL_URL = "https://raw.githubusercontent.com/oyyd/frozen_east_text_detection.pb/master/frozen_east_text_detection.pb"
    EAST_MODEL_PATH = "east_text_detection.pb"
    
    def __init__(self):
        self.net = None
        self._load_model()
        
    def _load_model(self):
        import os, urllib.request
        if not os.path.exists(self.EAST_MODEL_PATH):
            logger.info(f"Downloading EAST text detection model...")
            try:
                urllib.request.urlretrieve(self.EAST_MODEL_URL, self.EAST_MODEL_PATH)
                logger.info("EAST model downloaded.")
            except Exception as e:
                logger.warning(f"Could not download EAST model: {e}. Will use fallback contour-based detection.")
                return
        try:
            self.net = cv2.dnn.readNet(self.EAST_MODEL_PATH)
            logger.info("EAST Text Detector loaded successfully.")
        except Exception as e:
            logger.warning(f"Failed to load EAST model: {e}. Using contour-based fallback.")

    def detect(self, frame):
        """
        Detect text regions in a frame.
        Returns: list of dicts with 'box' [x1, y1, x2, y2] and 'score'.
        """
        if self.net is not None:
            return self._east_detect(frame)
        return self._contour_detect(frame)

    def _east_detect(self, frame):
        orig_h, orig_w = frame.shape[:2]
        # EAST requires dimensions divisible by 32
        new_w = max(320, (orig_w // 32) * 32)
        new_h = max(320, (orig_h // 32) * 32)

        blob = cv2.dnn.blobFromImage(frame, 1.0, (new_w, new_h),
                                     (123.68, 116.78, 103.94), swapRB=True, crop=False)
        self.net.setInput(blob)
        try:
            scores, geometry = self.net.forward(
                ["feature_fusion/Conv_7/Sigmoid", "feature_fusion/concat_3"]
            )
        except Exception as e:
            logger.warning(f"EAST forward pass error: {e}")
            return self._contour_detect(frame)

        boxes = self._decode_predictions(scores, geometry, orig_w, orig_h, new_w, new_h)
        return boxes

    def _decode_predictions(self, scores, geometry, orig_w, orig_h, new_w, new_h):
        num_rows, num_cols = scores.shape[2:4]
        detections = []
        min_confidence = 0.5

        rW = orig_w / float(new_w)
        rH = orig_h / float(new_h)

        for y in range(num_rows):
            scores_data = scores[0, 0, y]
            x_data0 = geometry[0, 0, y]
            x_data1 = geometry[0, 1, y]
            x_data2 = geometry[0, 2, y]
            x_data3 = geometry[0, 3, y]
            angles_data = geometry[0, 4, y]

            for x in range(num_cols):
                if scores_data[x] < min_confidence:
                    continue
                offset_x = x * 4.0
                offset_y = y * 4.0
                angle = angles_data[x]
                cos_a = float(cv2.cos(angle) if hasattr(cv2, "cos") else __import__("math").cos(angle))
                sin_a = float(__import__("math").sin(angle))

                h_box = x_data0[x] + x_data2[x]
                w_box = x_data1[x] + x_data3[x]

                end_x = int(offset_x + cos_a * x_data1[x] + sin_a * x_data2[x])
                end_y = int(offset_y - sin_a * x_data1[x] + cos_a * x_data2[x])
                start_x = int(end_x - w_box)
                start_y = int(end_y - h_box)

                # Scale back to original frame dimensions
                start_x = int(start_x * rW)
                start_y = int(start_y * rH)
                end_x = int(end_x * rW)
                end_y = int(end_y * rH)

                detections.append({"box": [start_x, start_y, end_x, end_y], "score": float(scores_data[x])})
        return detections

    def _contour_detect(self, frame):
        """Fallback: find text-like regions using adaptive threshold + contours."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                       cv2.THRESH_BINARY_INV, 11, 2)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (20, 5))
        dilated = cv2.dilate(thresh, kernel, iterations=1)
        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        boxes = []
        h, w = frame.shape[:2]
        for cnt in contours:
            x, y, bw, bh = cv2.boundingRect(cnt)
            if bw > 50 and bh > 10 and bw < w * 0.9:
                boxes.append({"box": [x, y, x + bw, y + bh], "score": 0.7})
        return boxes
