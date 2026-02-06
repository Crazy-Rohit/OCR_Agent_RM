import base64
from io import BytesIO
from PIL import Image

def pil_to_data_url(img: Image.Image, format: str = "PNG") -> tuple[str, int, int]:
    buf = BytesIO()
    img.save(buf, format=format)
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    data_url = f"data:image/{format.lower()};base64,{b64}"
    return data_url, img.size[0], img.size[1]
