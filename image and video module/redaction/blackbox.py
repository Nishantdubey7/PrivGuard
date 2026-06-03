import cv2

def apply_blackbox(frame, box):
    """Draws a solid black rectangle over the bounding box region."""
    x1, y1, x2, y2 = [int(v) for v in box]
    h, w = frame.shape[:2]
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)

    if x2 > x1 and y2 > y1:
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 0), -1)
        
    return frame
