from io import BytesIO

from PIL import Image

from src.image_preprocess import (
    crop_alipay_fund_area,
    load_image_from_uploaded_file,
    preprocess_mobile_screenshot,
    split_alipay_fund_rows,
)


def test_uploaded_image_is_rgb_and_rewound() -> None:
    buffer = BytesIO()
    Image.new("RGBA", (400, 900), (255, 255, 255, 255)).save(buffer, format="PNG")
    buffer.seek(0)
    image = load_image_from_uploaded_file(buffer)
    assert image.mode == "RGB"
    assert buffer.tell() == 0


def test_mobile_preprocess_crops_and_enlarges_without_binarizing() -> None:
    image = Image.new("RGB", (400, 900), (240, 40, 50))
    cropped = crop_alipay_fund_area(image)
    processed = preprocess_mobile_screenshot(cropped)
    assert cropped.height < image.height
    assert processed.size == (cropped.width * 2, cropped.height * 2)
    assert processed.mode == "RGB"


def test_row_split_has_safe_fallback() -> None:
    image = Image.new("RGB", (300, 600), "white")
    blocks = split_alipay_fund_rows(image)
    assert len(blocks) >= 1
