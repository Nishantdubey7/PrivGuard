import os
from pipeline.frame_extractor import FrameExtractor
from pipeline.video_builder import VideoBuilder
from pipeline.frame_processor import FrameProcessor
from audio.audio_connector import AudioConnector
from analytics.privacy_report_generator import PrivacyReportGenerator
from config.settings import REPORTS_DIR
from utils.logger import get_logger

logger = get_logger(__name__)

class VideoPipeline:
    def __init__(self, mode, identity_image_path=None):
        self.processor = FrameProcessor(mode, identity_image_path)
        self.audio_connector = AudioConnector()
        self.report_generator = PrivacyReportGenerator()
        
    def process_video(self, input_video_path):
        logger.info(f"Starting Video Pipeline for {input_video_path}")
        
        # 1. Setup extractors and builders
        extractor = FrameExtractor(input_video_path)
        filename = os.path.basename(input_video_path)
        base_name, _ = os.path.splitext(filename)
        output_video_path = f"output_redacted_{base_name}.mp4"
        
        builder = VideoBuilder(output_video_path, extractor.fps, extractor.width, extractor.height)
        
        # 2. Extract Audio
        temp_audio = "temp_audio.wav"
        temp_redacted_audio = "temp_redacted_audio.wav"
        self.audio_connector.extract_audio(input_video_path, temp_audio)
        self.audio_connector.redact_audio(temp_audio, temp_redacted_audio)
        
        # 3. Process Frames
        frame_count = 0
        all_stats = []
        for frame in extractor.get_frames():
            processed_frame, frame_stats = self.processor.process_frame(frame, frame_count)
            builder.write_frame(processed_frame)
            all_stats.extend(frame_stats)
            frame_count += 1
            if frame_count % 30 == 0:
                logger.info(f"Processed {frame_count}/{extractor.total_frames} frames")
                
        extractor.release()
        builder.release()
        
        # 4. Generate Report Stats
        self.report_generator.stats["video_duration_sec"] = frame_count / extractor.fps if extractor.fps else 0
        
        faces = len([s for s in all_stats if s["type"] == "face"])
        plates = len([s for s in all_stats if s["type"] == "plate"])
        
        self.report_generator.stats["faces_redacted"] = faces
        self.report_generator.stats["plates_redacted"] = plates
        
        piis = [s for s in all_stats if s["type"] not in ("face", "plate")]
        for p in piis:
            ptype = p["type"]
            self.report_generator.stats["pii_detected"][ptype] = self.report_generator.stats["pii_detected"].get(ptype, 0) + 1
            
        report_path = self.report_generator.generate_report()
        
        # 5. Merge Audio (or just finalize the video if ffmpeg not available)
        import shutil
        final_output = f"video_output/privguarded_{base_name}.mp4"
        if self.audio_connector.ffmpeg_available:
            self.audio_connector.merge_audio_video(output_video_path, temp_redacted_audio, final_output)
        else:
            logger.warning("ffmpeg not available. Final video will have no audio.")
            shutil.copy2(output_video_path, final_output)
        
        logger.info(f"Pipeline complete. Final video saved to {final_output}")
        logger.info(f"Privacy Report saved to {report_path}")
        return final_output, report_path
