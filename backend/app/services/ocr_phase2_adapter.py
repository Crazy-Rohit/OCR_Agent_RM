"""
Copy this adapter into your existing OCR flow.

Goal: return page image + bbox layout so frontend can show overlays.
"""
from typing import Dict, Any, List
from PIL import Image
from app.services.layout_service import build_layout
from app.utils.table_detection import detect_tables
from app.utils.image_encode import pil_to_data_url

def build_page_response(page_number: int, page_img: Image.Image, words: List[Dict[str, Any]]) -> Dict[str, Any]:
    layout = build_layout(words)
    tables = detect_tables(page_img)

    data_url, w, h = pil_to_data_url(page_img)

    return {
        "page_number": page_number,
        "image_base64": data_url,
        "width": w,
        "height": h,
        "words": words,
        "lines": layout.get("lines", []),
        "blocks": layout.get("blocks", []),
        "tables": tables,
    }
