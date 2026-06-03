import os

def ensure_dir(path: str):
    """Ensures that a directory exists."""
    os.makedirs(path, exist_ok=True)

def draw_boxes(image, boxes, color=(0, 255, 0), thickness=2):
    """Helper mock to draw boxes on image, used mostly for debugging."""
    import cv2
    for box in boxes:
        x1, y1, x2, y2 = [int(v) for v in box[:4]]
        cv2.rectangle(image, (x1, y1), (x2, y2), color, thickness)
    return image
