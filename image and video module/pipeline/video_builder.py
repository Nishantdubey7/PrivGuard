import cv2
from utils.logger import get_logger

logger = get_logger(__name__)

class VideoBuilder:
    def __init__(self, output_path, fps, width, height):
        self.output_path = output_path
        self.fps = fps
        self.width = width
        self.height = height
        
        # We use mp4v codec for standard mp4 files
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        self.writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
        logger.info(f"Initialized VideoBuilder for {output_path}")
        
    def write_frame(self, frame):
        self.writer.write(frame)
        
    def release(self):
        self.writer.release()
        logger.info(f"Video finalized at {self.output_path}")
