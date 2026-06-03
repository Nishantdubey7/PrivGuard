import cv2

def apply_pixelate(frame, box, blocks=10):
    """Applies a pixelation effect to the bounding box region."""
    x1, y1, x2, y2 = [int(v) for v in box]
    h, w = frame.shape[:2]
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)

    if x2 > x1 and y2 > y1:
        roi = frame[y1:y2, x1:x2]
        roi_h, roi_w = roi.shape[:2]
        
        # Determine step size
        w_step = max(1, roi_w // blocks)
        h_step = max(1, roi_h // blocks)

        small = cv2.resize(roi, (w_step, h_step), interpolation=cv2.INTER_LINEAR)
        pixelated = cv2.resize(small, (roi_w, roi_h), interpolation=cv2.INTER_NEAREST)
        frame[y1:y2, x1:x2] = pixelated
        
    return frame
