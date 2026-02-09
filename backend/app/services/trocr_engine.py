from __future__ import annotations

from typing import List, Tuple
from PIL import Image

import torch
from transformers import TrOCRProcessor, VisionEncoderDecoderModel

_PROCESSOR = None
_MODEL = None


def _get_model():
    global _PROCESSOR, _MODEL
    if _PROCESSOR is None or _MODEL is None:
        _PROCESSOR = TrOCRProcessor.from_pretrained("microsoft/trocr-base-handwritten")
        _MODEL = VisionEncoderDecoderModel.from_pretrained("microsoft/trocr-base-handwritten")
        _MODEL.eval()
    return _PROCESSOR, _MODEL


def trocr_ocr_crops(page_image: Image.Image, crops: List[Tuple[int, int, int, int]]) -> List[str]:
    processor, model = _get_model()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(device)

    images: List[Image.Image] = []
    for (x1, y1, x2, y2) in crops:
        images.append(page_image.crop((x1, y1, x2, y2)).convert("RGB"))

    pixel_values = processor(images=images, return_tensors="pt").pixel_values.to(device)
    with torch.no_grad():
        generated_ids = model.generate(pixel_values)

    texts = processor.batch_decode(generated_ids, skip_special_tokens=True)
    return [t.strip() for t in texts]
