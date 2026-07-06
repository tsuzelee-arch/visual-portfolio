"""Rescan resource/banner, rewrite images.json, and inject BANNER_MANIFEST into index.html.

Run from the repo root (or anywhere -- paths are resolved relative to this file):

    python tools/update_banner_gallery.py

Re-run whenever banner images are added, removed, or replaced.
"""

from __future__ import annotations

import json
import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BANNER_DIR = ROOT / "resource" / "banner"
IMAGES_JSON = ROOT / "images.json"
INDEX_HTML = ROOT / "index.html"

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}

MANIFEST_PATTERN = re.compile(
    r"/\* BANNER_MANIFEST:START \*/.*?/\* BANNER_MANIFEST:END \*/",
    re.DOTALL,
)

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def read_png_size(data: bytes) -> tuple[int, int] | None:
    if len(data) < 24 or data[:8] != PNG_SIGNATURE or data[12:16] != b"IHDR":
        return None
    width, height = struct.unpack(">II", data[16:24])
    return width, height


def read_jpeg_size(path: Path) -> tuple[int, int] | None:
    sof_markers = set(range(0xC0, 0xC4)) | set(range(0xC5, 0xC8)) | set(range(0xC9, 0xCC)) | set(range(0xCD, 0xD0))
    with path.open("rb") as handle:
        if handle.read(2) != b"\xff\xd8":
            return None
        while True:
            byte = handle.read(1)
            if not byte:
                return None
            if byte != b"\xff":
                continue
            marker = handle.read(1)
            while marker == b"\xff":
                marker = handle.read(1)
            if not marker:
                return None
            code = marker[0]
            if 0xD0 <= code <= 0xD9:
                continue
            length_bytes = handle.read(2)
            if len(length_bytes) != 2:
                return None
            (length,) = struct.unpack(">H", length_bytes)
            if code in sof_markers:
                body = handle.read(5)
                if len(body) != 5:
                    return None
                height, width = struct.unpack(">HH", body[1:5])
                return width, height
            handle.seek(length - 2, 1)


def read_image_size(path: Path) -> tuple[int, int]:
    try:
        from PIL import Image  # type: ignore

        with Image.open(path) as image:
            return image.size
    except ImportError:
        pass

    header = path.read_bytes()[:64]
    size = read_png_size(header)
    if size is None and path.suffix.lower() in {".jpg", ".jpeg"}:
        size = read_jpeg_size(path)
    if size is None:
        raise ValueError(f"Cannot read dimensions (install Pillow for non-PNG/JPEG formats): {path}")
    return size


def numeric_stem_key(path: Path) -> tuple[int, str]:
    stem = path.stem
    return (int(stem), stem) if stem.isdigit() else (10**9, stem)


def collect_images() -> list[dict]:
    if not BANNER_DIR.is_dir():
        sys.exit(f"Banner directory not found: {BANNER_DIR}")

    entries = []
    for path in sorted(BANNER_DIR.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        width, height = read_image_size(path)
        entries.append(
            {
                "path": path,
                "rel": path.relative_to(ROOT).as_posix(),
                "group": path.parent.name,
                "width": width,
                "height": height,
                "ratio": width / height,
            }
        )
    return entries


def write_images_json(entries: list[dict]) -> None:
    payload = [
        {
            "Path": entry["rel"],
            "Width": entry["width"],
            "Height": entry["height"],
            "Ratio": round(entry["ratio"], 2),
        }
        for entry in sorted(entries, key=lambda entry: entry["rel"])
    ]
    IMAGES_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=4) + "\n",
        encoding="utf-8",
    )


def build_manifest_js(entries: list[dict]) -> str:
    groups: dict[str, list[dict]] = {}
    for entry in entries:
        groups.setdefault(entry["group"], []).append(entry)

    def group_key(name: str) -> tuple[float, str]:
        members = groups[name]
        mean_ratio = sum(member["ratio"] for member in members) / len(members)
        return (mean_ratio, name)

    lines = []
    for name in sorted(groups, key=group_key):
        members = sorted(groups[name], key=lambda m: (m["ratio"], numeric_stem_key(m["path"])))
        for member in members:
            lines.append(
                f'  {{ src: "{member["rel"]}", w: {member["width"]}, h: {member["height"]}, g: "{name}" }},'
            )

    return (
        "/* BANNER_MANIFEST:START */\n"
        "const BANNER_MANIFEST = [\n" + "\n".join(lines) + "\n];\n"
        "/* BANNER_MANIFEST:END */"
    )


def inject_manifest(manifest_js: str) -> None:
    html = INDEX_HTML.read_text(encoding="utf-8")
    if not MANIFEST_PATTERN.search(html):
        sys.exit("BANNER_MANIFEST markers not found in index.html")
    INDEX_HTML.write_text(
        MANIFEST_PATTERN.sub(lambda _: manifest_js, html),
        encoding="utf-8",
    )


def main() -> None:
    entries = collect_images()
    write_images_json(entries)
    inject_manifest(build_manifest_js(entries))
    group_count = len({entry["group"] for entry in entries})
    print(f"Updated images.json and index.html: {len(entries)} images in {group_count} groups.")


if __name__ == "__main__":
    main()
