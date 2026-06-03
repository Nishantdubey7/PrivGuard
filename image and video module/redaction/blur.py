import cv2

def apply_blur(frame, box, ksize=(31, 31)):
    """Applies Gaussian Blur to the bounding box region."""
    x1, y1, x2, y2 = [int(v) for v in box]
    # Bound checks
    h, w = frame.shape[:2]
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)
    
    if x2 > x1 and y2 > y1:
        roi = frame[y1:y2, x1:x2]
        frame[y1:y2, x1:x2] = cv2.GaussianBlur(roi, ksize, 0)
    return frame
