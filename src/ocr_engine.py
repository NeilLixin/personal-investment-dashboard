from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Iterable

import numpy as np
from PIL import Image


@dataclass
class OCRStatus:
    available: bool
    message: str


class LocalOCREngine:
    def __init__(self) -> None:
        self.engine = None
        self.error = ""
        try:
            from rapidocr_onnxruntime import RapidOCR

            self.engine = RapidOCR()
        except Exception as exc:  # Optional dependency must never block app startup.
            self.error = str(exc)

    @property
    def status(self) -> OCRStatus:
        if self.engine:
            return OCRStatus(True, "本地 OCR 已启用（RapidOCR）")
        return OCRStatus(False, "OCR 组件未安装或初始化失败；可先使用手动粘贴 OCR 文本。")

    def recognize_image(self, image: Image.Image) -> str:
        if not self.engine:
            raise RuntimeError(f"OCR 组件未安装或初始化失败：{self.error or 'rapidocr-onnxruntime 不可用'}")
        result, _ = self.engine(np.asarray(image.convert("RGB")))
        if not result:
            return ""
        lines = []
        for item in result:
            if len(item) >= 2 and str(item[1]).strip():
                lines.append(str(item[1]).strip())
        return "\n".join(lines)

    def recognize_files(self, files: Iterable) -> tuple[str, list[str]]:
        sections, errors = [], []
        for index, file in enumerate(files, start=1):
            name = getattr(file, "name", f"截图{index}")
            try:
                raw = file.getvalue() if hasattr(file, "getvalue") else file.read()
                image = Image.open(BytesIO(raw))
                text = self.recognize_image(image)
                sections.append(f"## {name}\n{text or '[未识别到文字]'}")
            except Exception as exc:
                errors.append(f"{name}: {exc}")
        return "\n\n".join(sections), errors


def get_ocr_status() -> OCRStatus:
    return LocalOCREngine().status
