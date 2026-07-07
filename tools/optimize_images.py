"""Back up resource/ images, then downsize + recompress them for web display.

Run from anywhere (paths resolve relative to this file):

    python tools/optimize_images.py

What it does:
  1. Copies every current image under resource/ (excluding videos) into
     backups/originals-<today>/resource/, preserving folder structure.
  2. For each image under resource/banner/, resource/導購頁作品/, and
     resource/人物一致性演示/: shrinks it so its longest side is at most
     MAX_DIMENSION, and re-saves it. Images with no real transparent pixels
     are converted to JPEG (much smaller for photographic content); images
     with genuine transparency stay PNG.
  3. Writes a rename log (old relative path -> new relative path) to
     tools/optimize_rename_log.json so index.html references can be checked
     against it.

Re-run tools/update_banner_gallery.py afterwards to refresh images.json /
BANNER_MANIFEST with the new filenames and dimensions.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None  # these are legitimate oversized screenshots, not decompression bombs

ROOT = Path(__file__).resolve().parent.parent
TARGET_DIRS = [
    ROOT / "resource" / "banner",
    ROOT / "resource" / "導購頁作品",
    ROOT / "resource" / "人物一致性演示",
]
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
MAX_DIMENSION = 2200
SHORT_SIDE_FLOOR = 1600  # protects legibility on extreme-aspect images (e.g. full-page screenshots)
JPEG_QUALITY = 85


def compute_scale(width: int, height: int) -> float:
    long_side = max(width, height)
    short_side = min(width, height)

    scale = MAX_DIMENSION / long_side if long_side > MAX_DIMENSION else 1.0

    if short_side * scale < SHORT_SIDE_FLOOR:
        scale = min(1.0, SHORT_SIDE_FLOOR / short_side)

    return scale


def backup_originals(today: str) -> Path:
    backup_root = ROOT / "backups" / f"originals-{today}" / "resource"
    for target_dir in TARGET_DIRS:
        if not target_dir.is_dir():
            continue
        for path in target_dir.rglob("*"):
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
                dest = backup_root / path.relative_to(ROOT / "resource")
                dest.parent.mkdir(parents=True, exist_ok=True)
                if not dest.exists():
                    shutil.copy2(path, dest)
    return backup_root


def has_real_transparency(image: Image.Image, threshold: float = 0.005, alpha_cutoff: int = 250) -> bool:
    """True only if a meaningful portion of the image is actually transparent.

    Screenshot exports often carry a stray non-opaque edge pixel or two despite
    being visually fully opaque; a bare `alpha.getextrema()` check would wrongly
    keep those as uncompressible PNGs. Require >0.5% of pixels to be genuinely
    non-opaque before treating the image as having real transparency.
    """
    if image.mode not in ("RGBA", "LA"):
        return False
    alpha = image.getchannel("A")
    lo, _hi = alpha.getextrema()
    if lo == 255:
        return False
    fraction_non_opaque = (np.asarray(alpha) < alpha_cutoff).mean()
    return fraction_non_opaque > threshold


def optimize_one(path: Path) -> str | None:
    """Returns the new relative (to resource/) path if it changed, else None."""
    rel_before = path.relative_to(ROOT / "resource").as_posix()

    with Image.open(path) as image:
        image.load()
        scale = compute_scale(image.width, image.height)
        if scale < 1.0:
            new_size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
            image = image.resize(new_size, Image.LANCZOS)

        transparent = has_real_transparency(image)

        if transparent:
            out_path = path
            image.save(out_path, format="PNG", optimize=True)
        else:
            out_path = path.with_suffix(".jpg")
            rgb = image.convert("RGB")
            rgb.save(out_path, format="JPEG", quality=JPEG_QUALITY, optimize=True)
            if out_path != path:
                path.unlink()

    rel_after = out_path.relative_to(ROOT / "resource").as_posix()
    return rel_after if rel_after != rel_before else None


def main() -> None:
    from datetime import date

    today = date.today().isoformat() if len(sys.argv) < 2 else sys.argv[1]

    backup_root = backup_originals(today)
    print(f"Backed up originals to {backup_root}")

    renames: dict[str, str] = {}
    before_total = 0
    after_total = 0
    count = 0

    for target_dir in TARGET_DIRS:
        if not target_dir.is_dir():
            continue
        for path in sorted(target_dir.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in IMAGE_SUFFIXES:
                continue
            rel_before = path.relative_to(ROOT / "resource").as_posix()
            before_total += path.stat().st_size
            new_rel = optimize_one(path)
            count += 1
            final_path = ROOT / "resource" / (new_rel or rel_before)
            after_total += final_path.stat().st_size
            if new_rel:
                renames[rel_before] = new_rel

    log_path = Path(__file__).resolve().parent / "optimize_rename_log.json"
    log_path.write_text(json.dumps(renames, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Optimized {count} images.")
    print(f"Total size: {before_total / 1024 / 1024:.1f}MB -> {after_total / 1024 / 1024:.1f}MB")
    print(f"Renamed {len(renames)} files (extension changes); log: {log_path}")
    for old, new in renames.items():
        print(f"  {old} -> {new}")


if __name__ == "__main__":
    main()
