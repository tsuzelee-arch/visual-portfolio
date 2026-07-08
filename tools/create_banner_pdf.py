"""Create a single PDF file containing all images in resource/banner/ recursively.

Run from repository root:
    python tools/create_banner_pdf.py
"""

import sys
import re
from pathlib import Path
from PIL import Image

# Setup paths
ROOT = Path(__file__).resolve().parent.parent
BANNER_DIR = ROOT / "resource" / "banner"
OUTPUT_PDF = ROOT / "banner_images.pdf"

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}

def split_num_str(s: str):
    """Splits a string into chunks of digits and non-digits for type-safe natural sorting."""
    parts = []
    for part in re.split(r'(\d+)', s):
        if not part:
            continue
        if part.isdigit():
            parts.append((0, int(part)))  # 0: number
        else:
            parts.append((1, part.lower()))  # 1: string
    return tuple(parts)

def path_sort_key(path: Path):
    """Generates a natural sorting key for paths based on relative path parts."""
    rel_path = path.relative_to(BANNER_DIR)
    key_parts = []
    for part in rel_path.parts:
        key_parts.append(split_num_str(part))
    return tuple(key_parts)

def to_rgb(image: Image.Image) -> Image.Image:
    """Safely converts any image mode to RGB, flattening transparency onto a white background."""
    if image.mode == 'RGB':
        return image
    if image.mode in ('RGBA', 'LA') or (image.mode == 'P' and 'transparency' in image.info):
        # Create a white background of the same size
        bg = Image.new('RGB', image.size, (255, 255, 255))
        # Convert image to RGBA to ensure it has an alpha channel
        rgba_img = image.convert('RGBA')
        # Paste using the alpha channel as a mask
        bg.paste(rgba_img, mask=rgba_img.split()[3])
        return bg
    else:
        return image.convert('RGB')

def main() -> None:
    if not BANNER_DIR.is_dir():
        print(f"Error: Banner directory not found at {BANNER_DIR}", file=sys.stderr)
        sys.exit(1)

    print("Scanning for banner images...")
    image_paths = []
    for path in BANNER_DIR.rglob("*"):
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
            image_paths.append(path)

    if not image_paths:
        print("No images found in the banner directory.", file=sys.stderr)
        sys.exit(1)

    # Sort images naturally
    image_paths.sort(key=path_sort_key)
    print(f"Found {len(image_paths)} images. Sorting complete.")

    processed_images = []
    print("Processing images and converting to RGB...")
    for idx, path in enumerate(image_paths, 1):
        rel_path = path.relative_to(ROOT)
        print(f"[{idx}/{len(image_paths)}] Processing {rel_path}...")
        try:
            with Image.open(path) as img:
                # Load the first frame (relevant for GIFs)
                img.seek(0)
                # Convert to RGB with white background
                rgb_img = to_rgb(img)
                # We need to keep the image data in memory, so we call load()
                rgb_img.load()
                processed_images.append(rgb_img)
        except Exception as e:
            print(f"Warning: Failed to process image {path}. Error: {e}", file=sys.stderr)

    if not processed_images:
        print("Error: No images were successfully processed.", file=sys.stderr)
        sys.exit(1)

    print(f"Saving compiled PDF to {OUTPUT_PDF}...")
    try:
        # Save the first image, and append the rest
        first_img = processed_images[0]
        rest_imgs = processed_images[1:]
        
        # We can also pass quality parameter if needed to reduce file size.
        # Pillow's PDF writer supports quality parameter when saving.
        first_img.save(
            OUTPUT_PDF,
            save_all=True,
            append_images=rest_imgs,
            resolution=100.0,
            quality=85
        )
        print("PDF compilation complete!")
        print(f"PDF Size: {OUTPUT_PDF.stat().st_size / 1024 / 1024:.2f} MB")
    except Exception as e:
        print(f"Error saving PDF: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
