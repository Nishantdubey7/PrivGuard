import argparse
import sys
from pipeline.video_pipeline import VideoPipeline
from config.settings import RedactionMode

def parse_args():
    parser = argparse.ArgumentParser(description="RE-DACT Video Redaction Engine")
    parser.add_argument("--video", type=str, required=True, help="Input video path")
    parser.add_argument("--mode", type=int, choices=[1, 2, 3, 4], required=True, 
                        help="Redaction mode (1: Face, 2: Plate+PII, 3: Face+Plate+PII, 4: Identity Protect)")
    parser.add_argument("--identity", type=str, default=None, 
                        help="Path to identity reference image (required for mode 4)")
    return parser.parse_args()

def main():
    args = parse_args()
    
    if args.mode == RedactionMode.IDENTITY_PROTECT and not args.identity:
        print("Error: --identity image path is required for mode 4 (Identity Protection)")
        sys.exit(1)
        
    print(f"Starting RE-DACT Engine")
    print(f"Target Video: {args.video}") 
    print(f"Redaction Mode: {args.mode}")
    if args.identity:
        print(f"Authorized Identity Profile: {args.identity}")
        
    pipeline = VideoPipeline(mode=args.mode, identity_image_path=args.identity)
    try:
        final_video, report_path = pipeline.process_video(args.video)
        print("\n--- Processing Complete ---")
        print(f"Redacted Video: {final_video}")
        print(f"Privacy Report: {report_path}")
    except Exception as e:
        print(f"An error occurred during processing: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
