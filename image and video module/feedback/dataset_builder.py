import os
from config.settings import FEEDBACK_DIR

class DatasetBuilder:
    def __init__(self):
        self.feedback_dir = FEEDBACK_DIR

    def export_yolo_format(self, output_dir):
        """
        Converts logged feedback annotations into YOLO training format.
        (Mock Implementation)
        """
        pass
