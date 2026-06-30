from io import BytesIO

from PIL import Image
from streamlit.testing.v1 import AppTest


def test_uploaded_image_enables_ocr_button() -> None:
    buffer = BytesIO()
    Image.new("RGB", (12, 12), "white").save(buffer, format="PNG")
    app = AppTest.from_file("app.py", default_timeout=10).run()
    app.radio[0].set_value("截图导入").run()
    app.file_uploader[0].set_value(("sample.png", buffer.getvalue(), "image/png")).run()
    ocr_button = next(button for button in app.button if button.label == "开始本地 OCR")
    assert ocr_button.disabled is False
    assert any("已上传 1 张图片" in item.value for item in app.markdown)
    assert any("sample.png" in item.value for item in app.markdown)
