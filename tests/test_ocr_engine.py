from io import BytesIO

import pytest
from PIL import Image

from src.ocr_engine import (
    LocalOCREngine,
    get_ocr_status,
    is_ocr_available,
    normalize_ocr_result,
    normalize_rapidocr_result,
)


class UploadedFileStub(BytesIO):
    def __init__(self, raw: bytes, name: str):
        super().__init__(raw)
        self.name = name

    def getvalue(self) -> bytes:
        return super().getvalue()


def _png_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (16, 16), "white").save(buffer, format="PNG")
    return buffer.getvalue()


def test_status_without_optional_dependency_never_crashes() -> None:
    status = get_ocr_status()
    assert isinstance(status.available, bool)
    assert status.state in {"available", "unavailable", "initialization_failed"}
    assert status.engine == "RapidOCR"


def test_is_ocr_available_returns_bool() -> None:
    assert isinstance(is_ocr_available(), bool)


def test_normalize_rapidocr_result() -> None:
    result = ([[[0, 0], [1, 0], [1, 1], [0, 1]], "支付宝基金", 0.99],
              [[[0, 2], [1, 2], [1, 3], [0, 3]], "持有金额 123.45", 0.98])
    assert normalize_ocr_result((result, {"elapsed": 0.1})) == "支付宝基金\n持有金额 123.45"
    normalized = normalize_rapidocr_result((result, {"elapsed": 0.1}))
    assert len(normalized["items"]) == 2
    assert normalized["items"][0]["score"] == 0.99
    assert normalized["items"][1]["center_y"] == pytest.approx(2.5)


def test_empty_and_invalid_image_are_graceful() -> None:
    engine = LocalOCREngine()
    engine.engine = lambda image: ([], None)  # Reach image validation independent of installed OCR package.
    engine.state = "available"
    empty = engine.recognize_image(b"")
    invalid = engine.recognize_image(b"not an image")
    assert empty["ok"] is False and empty["error"]
    assert invalid["ok"] is False and invalid["error"]


def test_multiple_images_keep_success_when_one_fails() -> None:
    engine = LocalOCREngine()
    engine.engine = lambda image: ([([0, 0, 1, 1], "识别成功", 0.9)], None)
    engine.state = "available"
    good = UploadedFileStub(_png_bytes(), "good.png")
    bad = UploadedFileStub(b"broken", "bad.png")
    result = engine.recognize_images([good, bad])
    assert result["ok"] is True
    assert result["details"]["success_count"] == 1
    assert result["details"]["failure_count"] == 1
    assert "识别成功" in result["text"] and "bad.png" in result["error"]
    assert result["details"]["results"][0]["items"][0]["center_x"] == pytest.approx(0.5)
    assert good.tell() == 0 and bad.tell() == 0
