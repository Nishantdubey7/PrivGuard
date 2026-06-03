import sys
import cv2
import argparse
import os
from pipeline.image_processor import ImageProcessor
from config.settings import RedactionMode

def parse_args():
    parser = argparse.ArgumentParser(description="RE-DACT Image Redaction Engine")
    parser.add_argument("--image", type=str, required=True, help="Input image path")
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
        
    print(f"Starting Privguard Engine for Image")
    print(f"Target Image: {args.image}") 
    print(f"Redaction Mode: {args.mode}")
    if args.identity:
        print(f"Authorized Identity Profile: {args.identity}")
        
    if not os.path.exists(args.image):
        print(f"Error: Image {args.image} not found.")
        sys.exit(1)

    # Read image
    image = cv2.imread(args.image)
    if image is None:
        print(f"Error: Could not read image {args.image}.")
        sys.exit(1)

    # Initialize Processor
    processor = ImageProcessor(mode=args.mode, identity_image_path=args.identity)
    
    # Process Image
    try:
        processed_image, stats = processor.process_image(image)
        
        # Save Output
        filename = os.path.basename(args.image)
        base_name, ext = os.path.splitext(filename)
        output_image_path = f"image_output/privguarded_{base_name}{ext}"
        
        cv2.imwrite(output_image_path, processed_image)
        
        print("\n--- Processing Complete ---")
        print(f"Redacted Image: {output_image_path}")
        print("Redaction Stats:")
        for stat in stats:
            print(f" - Redacted: {stat['type']}")
    except Exception as e:
        print(f"An error occurred during processing: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
