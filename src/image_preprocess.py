from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from src.config import EXPORTS_DIR


def load_image_from_uploaded_file(uploaded_file: Any) -> Image.Image:
    """Load a Streamlit upload safely, normalize EXIF orientation, and rewind it."""
    if hasattr(uploaded_file, "seek"):
        uploaded_file.seek(0)
    try:
        image = Image.open(uploaded_file)
        image.load()
        return ImageOps.exif_transpose(image).convert("RGB")
    finally:
        if hasattr(uploaded_file, "seek"):
            uploaded_file.seek(0)


def crop_alipay_fund_area(image: Image.Image) -> Image.Image:
    """Remove common Alipay status/header/tab bars while retaining the holdings card."""
    source = ImageOps.exif_transpose(image).convert("RGB")
    width, height = source.size
    if width < 300 or height / max(width, 1) < 1.35:
        return source
    top = int(height * 0.10)
    bottom = int(height * 0.92)
    if bottom - top < height * 0.60:
        return source
    cropped = source.crop((0, top, width, bottom))
    cropped.info["ocr_offset_y"] = top
    return cropped


def preprocess_mobile_screenshot(image: Image.Image, scale: int = 2) -> Image.Image:
    """Upscale and lightly enhance a mobile screenshot without destroying red/green text."""
    source = ImageOps.exif_transpose(image).convert("RGB")
    scale = 3 if scale >= 3 else 2
    enlarged = source.resize((source.width * scale, source.height * scale), Image.Resampling.LANCZOS)
    contrasted = ImageEnhance.Contrast(enlarged).enhance(1.12)
    sharpened = contrasted.filter(ImageFilter.UnsharpMask(radius=1.2, percent=135, threshold=3))
    sharpened.info["ocr_offset_y"] = int(source.info.get("ocr_offset_y", 0) * scale)
    return sharpened


def split_alipay_fund_rows(image: Image.Image) -> list[Image.Image]:
    """Split on long pale horizontal separators; return the full image when confidence is low."""
    source = image.convert("RGB")
    gray = np.asarray(source.convert("L"), dtype=np.float32)
    height, width = gray.shape
    if height < 500 or width < 300:
        return [source]
    sample = gray[:, int(width * 0.04): int(width * 0.96)]
    row_mean = sample.mean(axis=1)
    row_std = sample.std(axis=1)
    candidates = np.where((row_mean >= 225) & (row_mean <= 252) & (row_std <= 7))[0].tolist()
    centers: list[int] = []
    for y in candidates:
        if not centers or y - centers[-1] > 8:
            centers.append(y)
        else:
            centers[-1] = (centers[-1] + y) // 2
    minimum_gap = max(120, int(height * 0.035))
    boundaries = [0]
    for y in centers:
        if y - boundaries[-1] >= minimum_gap and height - y >= minimum_gap:
            boundaries.append(y)
    boundaries.append(height)
    blocks: list[Image.Image] = []
    base_offset = int(source.info.get("ocr_offset_y", 0))
    for start, end in zip(boundaries, boundaries[1:]):
        if end - start < minimum_gap:
            continue
        block = source.crop((0, max(0, start - 8), width, min(height, end + 8)))
        block.info["ocr_offset_y"] = base_offset + max(0, start - 8)
        blocks.append(block)
    return blocks if 2 <= len(blocks) <= 24 else [source]


def save_ocr_debug_images(images: Iterable[Image.Image], prefix: str) -> list[Path]:
    """Persist opt-in OCR diagnostics below ignored data/exports/ocr_debug/."""
    target_dir = EXPORTS_DIR / "ocr_debug"
    target_dir.mkdir(parents=True, exist_ok=True)
    safe_prefix = "".join(char if char.isalnum() or char in "-_" else "_" for char in prefix)[:60] or "ocr"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    paths: list[Path] = []
    for index, image in enumerate(images, start=1):
        path = target_dir / f"{safe_prefix}_{stamp}_{index:02d}.png"
        image.convert("RGB").save(path, format="PNG")
        paths.append(path)
    return paths
