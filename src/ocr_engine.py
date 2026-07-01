from __future__ import annotations

from dataclasses import asdict, dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError


ENGINE_NAME = "RapidOCR"
INSTALL_COMMAND = "pip install -r requirements-ocr.txt"
MAX_IMAGE_SIDE = 4096
MAX_IMAGE_PIXELS = 40_000_000
MAX_INPUT_BYTES = 30 * 1024 * 1024


@dataclass(frozen=True)
class OCRStatus:
    available: bool
    state: str
    engine: str
    message: str
    error: str = ""
    install_command: str = INSTALL_COMMAND

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class LocalOCREngine:
    """Optional, failure-safe wrapper around rapidocr-onnxruntime."""

    def __init__(self) -> None:
        self.engine: Any | None = None
        self.error = ""
        self.state = "unavailable"
        try:
            from rapidocr_onnxruntime import RapidOCR
        except (ImportError, ModuleNotFoundError) as exc:
            self.error = str(exc) or "rapidocr-onnxruntime 未安装"
            return
        try:
            self.engine = RapidOCR()
            self.state = "available"
        except Exception as exc:  # Model/runtime initialization must not block app startup.
            self.state = "initialization_failed"
            self.error = f"{type(exc).__name__}: {exc}"

    @property
    def status(self) -> OCRStatus:
        if self.engine is not None:
            return OCRStatus(True, "available", ENGINE_NAME, "本地 OCR 可用")
        if self.state == "initialization_failed":
            return OCRStatus(False, self.state, ENGINE_NAME, "OCR 依赖已安装，但引擎初始化失败", self.error)
        return OCRStatus(False, "unavailable", ENGINE_NAME, "OCR 依赖未安装", self.error)

    def recognize_image(self, image_input: Any) -> dict[str, Any]:
        if self.engine is None:
            return _result(False, error=_unavailable_message(self.status), details={"status": self.status.to_dict()})
        try:
            image, source = _load_image(image_input)
            original_size = image.size
            image = ImageOps.exif_transpose(image).convert("RGB")
            if max(image.size) > MAX_IMAGE_SIDE:
                image.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE), Image.Resampling.LANCZOS)
            raw_result = self.engine(np.asarray(image))
            normalized = normalize_rapidocr_result(raw_result)
            return _result(True, text=normalized["text"], items=normalized["items"],
                           details={"source": source, "original_size": original_size,
                                    "processed_size": image.size, "line_count": len(normalized["items"])})
        except (ValueError, OSError, UnidentifiedImageError) as exc:
            return _result(False, error=f"图片无法读取：{exc}", details={"exception": type(exc).__name__})
        except Exception as exc:
            return _result(False, error=f"OCR 识别失败：{type(exc).__name__}: {exc}", details={"exception": type(exc).__name__})
        finally:
            _rewind(image_input)

    def recognize_images(self, uploaded_files: Iterable[Any]) -> dict[str, Any]:
        results, sections, errors, all_items = [], [], [], []
        for index, image_input in enumerate(list(uploaded_files or []), start=1):
            name = str(getattr(image_input, "name", f"截图{index}"))
            item = self.recognize_image(image_input)
            item["name"] = name
            results.append(item)
            if item["ok"]:
                sections.append(f"## {name}\n{item['text'] or '[未识别到文字]'}")
                for ocr_item in item.get("items", []):
                    all_items.append({**ocr_item, "source_name": name, "image_index": index - 1})
            else:
                errors.append(f"{name}: {item['error']}")
        if not results:
            return _result(False, error="没有可识别的图片", items=[],
                           details={"results": [], "success_count": 0, "failure_count": 0})
        return _result(bool(sections), text="\n\n".join(sections), items=all_items, error="；".join(errors),
                       details={"results": results, "success_count": len(sections), "failure_count": len(errors)})

    # Backward-compatible adapter for older callers.
    def recognize_files(self, files: Iterable[Any]) -> tuple[str, list[str]]:
        result = self.recognize_images(files)
        errors = [f"{item['name']}: {item['error']}" for item in result["details"]["results"] if not item["ok"]]
        return result["text"], errors


def _result(ok: bool, text: str = "", items: list[dict[str, Any]] | None = None,
            error: str = "", details: Any = None) -> dict[str, Any]:
    return {"ok": bool(ok), "text": text or "", "items": items or [], "error": error or "",
            "engine": "rapidocr", "details": details or {}}


def _unavailable_message(status: OCRStatus) -> str:
    reason = status.error or status.message
    return f"{status.message}：{reason}。请执行 `{INSTALL_COMMAND}`，安装后重启 Streamlit。"


def _rewind(image_input: Any) -> None:
    if hasattr(image_input, "seek"):
        try:
            image_input.seek(0)
        except (OSError, ValueError):
            pass


def _load_image(image_input: Any) -> tuple[Image.Image, str]:
    if isinstance(image_input, Image.Image):
        if image_input.width * image_input.height > MAX_IMAGE_PIXELS:
            raise ValueError("图片像素过大，请先压缩到 4000 万像素以内")
        return image_input.copy(), "PIL.Image"
    if isinstance(image_input, (bytes, bytearray, memoryview)):
        raw = bytes(image_input)
        return _image_from_bytes(raw), "bytes"
    if isinstance(image_input, (str, Path)):
        path = Path(image_input)
        if not path.is_file():
            raise ValueError(f"文件不存在：{path}")
        if path.stat().st_size > MAX_INPUT_BYTES:
            raise ValueError("图片文件过大，请先压缩到 30MB 以内")
        with Image.open(path) as opened:
            if opened.width * opened.height > MAX_IMAGE_PIXELS:
                raise ValueError("图片像素过大，请先压缩到 4000 万像素以内")
            opened.load()
            return opened.copy(), str(path)
    if hasattr(image_input, "getvalue"):
        raw = image_input.getvalue()
    elif hasattr(image_input, "read"):
        _rewind(image_input)
        raw = image_input.read()
    else:
        raise ValueError(f"不支持的图片输入类型：{type(image_input).__name__}")
    return _image_from_bytes(raw), str(getattr(image_input, "name", "uploaded_file"))


def _image_from_bytes(raw: bytes) -> Image.Image:
    if not raw:
        raise ValueError("文件为空")
    if len(raw) > MAX_INPUT_BYTES:
        raise ValueError("图片文件过大，请先压缩到 30MB 以内")
    image = Image.open(BytesIO(raw))
    if image.width * image.height > MAX_IMAGE_PIXELS:
        raise ValueError("图片像素过大，请先压缩到 4000 万像素以内")
    image.load()
    return image


def normalize_ocr_result(result: Any) -> str:
    """Normalize RapidOCR's `(lines, elapsed)` or line-list result into editable text."""
    return normalize_rapidocr_result(result)["text"]


def normalize_rapidocr_result(result: Any) -> dict[str, Any]:
    """Normalize real RapidOCR line tuples while retaining polygon and derived coordinates."""
    if result is None:
        return {"text": "", "items": []}
    lines = result[0] if isinstance(result, tuple) and result else result
    if not lines:
        return {"text": "", "items": []}
    if isinstance(lines, str):
        return {"text": lines.strip(), "items": []}
    items: list[dict[str, Any]] = []
    for item in lines:
        text, score, box = "", 0.0, []
        if isinstance(item, str):
            text = item
        elif isinstance(item, dict):
            text = str(item.get("text") or item.get("txt") or "")
            score = _safe_score(item.get("score", item.get("confidence", 0.0)))
            box = item.get("box") or item.get("points") or []
        elif isinstance(item, (list, tuple)):
            # RapidOCR line shape: [box, text, confidence].
            if len(item) >= 2 and isinstance(item[1], str):
                box = item[0]
                text = item[1]
                score = _safe_score(item[2] if len(item) >= 3 else 0.0)
            else:
                text = next((part for part in item if isinstance(part, str)), "")
        if text.strip():
            points = _normalize_box(box)
            xs = [point[0] for point in points]
            ys = [point[1] for point in points]
            min_x = min(xs) if xs else 0.0
            max_x = max(xs) if xs else 0.0
            min_y = min(ys) if ys else 0.0
            max_y = max(ys) if ys else 0.0
            items.append({"text": text.strip(), "score": score, "box": points,
                          "center_x": (min_x + max_x) / 2, "center_y": (min_y + max_y) / 2,
                          "min_x": min_x, "max_x": max_x, "min_y": min_y, "max_y": max_y})
    return {"text": "\n".join(item["text"] for item in items), "items": items}


def _normalize_box(box: Any) -> list[list[float]]:
    if isinstance(box, np.ndarray):
        box = box.tolist()
    if not isinstance(box, (list, tuple)):
        return []
    if len(box) == 4 and all(isinstance(value, (int, float)) for value in box):
        x1, y1, x2, y2 = map(float, box)
        return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]
    points: list[list[float]] = []
    for point in box:
        if isinstance(point, np.ndarray):
            point = point.tolist()
        if isinstance(point, (list, tuple)) and len(point) >= 2:
            try:
                points.append([float(point[0]), float(point[1])])
            except (TypeError, ValueError):
                continue
    return points


def _safe_score(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def get_ocr_status() -> OCRStatus:
    return LocalOCREngine().status


def is_ocr_available() -> bool:
    return bool(get_ocr_status().available)


def recognize_image(image_input: Any) -> dict[str, Any]:
    return LocalOCREngine().recognize_image(image_input)


def recognize_images(uploaded_files: Iterable[Any]) -> dict[str, Any]:
    return LocalOCREngine().recognize_images(uploaded_files)
