import cv2
import numpy as np
import dlib
from utils.logger import get_logger

logger = get_logger(__name__)

class FaceRecognizer:
    """
    Real face recognition using dlib's face_recognition_model_v1 (128-D embedding).
    Uses cosine distance threshold to match against authorized identities.
    """

    SIMILARITY_THRESHOLD = 0.5  # Lower = stricter match

    def __init__(self):
        import os
        import urllib.request
        import bz2

        logger.info("Initializing dlib face recognition model...")
        self.detector = dlib.get_frontal_face_detector()
        
        shape_model = "shape_predictor_68_face_landmarks.dat"
        rec_model = "dlib_face_recognition_resnet_model_v1.dat"
        shape_url = "http://dlib.net/files/shape_predictor_68_face_landmarks.dat.bz2"
        rec_url = "http://dlib.net/files/dlib_face_recognition_resnet_model_v1.dat.bz2"

        def download_and_extract(url, target_path):
            if os.path.exists(target_path):
                return True
            try:
                logger.info(f"Downloading missing model from {url}...")
                bz2_path = target_path + ".bz2"
                urllib.request.urlretrieve(url, bz2_path)
                logger.info(f"Extracting {bz2_path}...")
                with bz2.BZ2File(bz2_path, 'rb') as fr, open(target_path, 'wb') as fw:
                    fw.write(fr.read())
                os.remove(bz2_path)
                return True
            except Exception as e:
                logger.error(f"Failed to download/extract {url}: {e}")
                return False

        shape_ready = download_and_extract(shape_url, shape_model)
        rec_ready = download_and_extract(rec_url, rec_model)

        if shape_ready and rec_ready:
            try:
                self.shape_predictor = dlib.shape_predictor(shape_model)
                self.face_rec_model = dlib.face_recognition_model_v1(rec_model)
                self._model_ready = True
                logger.info("dlib face recognition model loaded successfully.")
            except Exception as e:
                logger.warning(f"Could not load dlib models: {e}. Face recognition disabled.")
                self._model_ready = False
        else:
            logger.warning("Missing dlib recognition models. Face recognition disabled.")
            self._model_ready = False

        self.authorized_embeddings = []

    def _get_embedding(self, frame, box=None):
        """Extract a 128-d face embedding from frame (and optionally crop to box)."""
        if not self._model_ready:
            return None
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        if box:
            x1, y1, x2, y2 = [int(v) for v in box]
            rect = dlib.rectangle(x1, y1, x2, y2)
        else:
            dets = self.detector(rgb)
            if not dets:
                return None
            rect = dets[0]
        shape = self.shape_predictor(rgb, rect)
        embedding = np.array(self.face_rec_model.compute_face_descriptor(rgb, shape))
        return embedding

    def load_authorized_identity(self, image_path):
        """Load reference image and store the embedding."""
        frame = cv2.imread(image_path)
        if frame is None:
            logger.error(f"Cannot read identity image: {image_path}")
            return
        emb = self._get_embedding(frame)
        if emb is not None:
            self.authorized_embeddings.append(emb)
            logger.info(f"Authorized identity loaded from {image_path}.")
        else:
            logger.warning(f"No face found in reference image: {image_path}")

    def is_authorized(self, frame, face_box):
        """
        Compare the face at face_box in frame against all authorized embeddings.
        Returns True if the face is a known authorized identity.
        """
        if not self.authorized_embeddings or not self._model_ready:
            return False

        query_emb = self._get_embedding(frame, face_box)
        if query_emb is None:
            return False

        for ref_emb in self.authorized_embeddings:
            dist = np.linalg.norm(query_emb - ref_emb)
            if dist < self.SIMILARITY_THRESHOLD:
                logger.info(f"Face recognized as AUTHORIZED (distance={dist:.3f}).")
                return True
        return False
