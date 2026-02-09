from __future__ import annotations

from typing import Any, Dict, List
from PIL import Image

from doctr.io import DocumentFile
from doctr.models import ocr_predictor

_PREDICTOR = None


def _get_predictor():
    global _PREDICTOR
    if _PREDICTOR is None:
        _PREDICTOR = ocr_predictor(pretrained=True)
    return _PREDICTOR


def doctr_ocr_page(image: Image.Image) -> Dict[str, Any]:
    predictor = _get_predictor()
    img = image.convert("RGB")
    doc = DocumentFile.from_images([img])
    result = predictor(doc)
    exported = result.export()

    full_text_parts: List[str] = []
    for page in exported.get("pages", []):
        for block in page.get("blocks", []):
            for line in block.get("lines", []):
                words = [w.get("value", "") for w in line.get("words", []) if w.get("value")]
                if words:
                    full_text_parts.append(" ".join(words))

    return {
        "text": "\n".join(full_text_parts).strip(),
        "raw": exported,
    }
