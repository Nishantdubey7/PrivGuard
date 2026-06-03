import os
import subprocess
import shutil
from utils.logger import get_logger
import requests

logger = get_logger(__name__)

def _get_ffmpeg():
    """Return path to ffmpeg binary, checking PATH and common install locations."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        return ffmpeg
    # Common Windows locations
    candidates = [
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    raise FileNotFoundError(
        "ffmpeg not found. Please install ffmpeg and add it to PATH.\n"
        "Download from: https://ffmpeg.org/download.html"
    )


class AudioConnector:
    def __init__(self):
        try:
            self.ffmpeg = _get_ffmpeg()
            self.ffmpeg_available = True
            logger.info(f"AudioConnector initialized. Using ffmpeg at: {self.ffmpeg}")
        except FileNotFoundError as e:
            self.ffmpeg_available = False
            self.ffmpeg = None
            logger.warning(f"{e}\nAudio extraction/merging will be skipped.")

    def extract_audio(self, video_path: str, output_audio_path: str):
        """Extracts audio stream from video using ffmpeg."""
        if not self.ffmpeg_available:
            return
        logger.info(f"Extracting audio from '{video_path}' → '{output_audio_path}'")
        cmd = [self.ffmpeg, "-y", "-i", video_path, "-q:a", "0", "-map", "a", output_audio_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.warning(f"Audio extraction failed (video may have no audio): {result.stderr[-200:]}")
        else:
            logger.info("Audio extraction complete.")

    # def redact_audio(self, input_audio_path: str, output_audio_path: str):
    #     """Sends audio to the external Audio Redaction Module, or passes through if unavailable."""
    #     if not self.ffmpeg_available or not os.path.exists(input_audio_path):
    #         return
    #     logger.info(f"Sending audio to external Audio Redaction module: {input_audio_path}")
    #     try:
    #         from audio_redaction_model import redact as external_redact  # type: ignore
    #         external_redact(input_audio_path, output_audio_path)
    #         logger.info("External audio redaction complete.")
    #     except ImportError:
    #         logger.warning("External audio_redaction_model not found. Passing audio through unchanged.")
    #         shutil.copy2(input_audio_path, output_audio_path)
    
    

    def redact_audio(self, input_audio_path: str, output_audio_path: str):
        """Send audio to external API for redaction."""
        
        if not self.ffmpeg_available or not os.path.exists(input_audio_path):
            return

        logger.info(f"Sending audio to external API: {input_audio_path}")

        try:
            url = "http://localhost:5000/api/audio"
            
            # url = "http://35.200.145.250/api/audio/lvl1"
            

            with open(input_audio_path, "rb") as f:
                files = {
                    "file": ("audio.wav", f, "audio/wav")
                }

                # ⏳ IMPORTANT: allow long processing
                response = requests.post(
                    url,
                    files=files,
                    data={"redaction_level": "1"},
                    stream=True,
                    timeout=60 * 10  # 10 mins
                )

            if response.status_code != 200:
                raise Exception(f"API failed: {response.status_code}")

            # ✅ Save streamed response to file
            with open(output_audio_path, "wb") as out:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        out.write(chunk)

            logger.info("Audio redaction via API complete.")

        except Exception as e:
            logger.warning(f"Audio API failed: {e}. Passing through original audio.")
            shutil.copy2(input_audio_path, output_audio_path)

    def merge_audio_video(self, video_path: str, audio_path: str, output_path: str):
        """
        Merges redacted audio back with the redacted video using ffmpeg.
        """
        if not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
            logger.warning("No valid audio file or ffmpeg unavailable. Copying video-only to output.")
            shutil.copy2(video_path, output_path)
            return

        logger.info(f"Merging video '{video_path}' + audio '{audio_path}' → '{output_path}'")
        cmd = [
            self.ffmpeg, "-y",
            "-i", video_path,
            "-i", audio_path,
            "-c:v", "libx264",
            "-c:a", "aac",
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-shortest",
            output_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.warning(f"Audio/video merge failed: {result.stderr[-300:]}. Copying video without audio.")
            shutil.copy2(video_path, output_path)
        else:
            logger.info(f"Merge complete → {output_path}")
