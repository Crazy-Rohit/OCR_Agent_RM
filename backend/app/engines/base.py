from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Protocol

from PIL import Image

from app.models.schemas import WordBox


@dataclass
class OcrResult:
    text: str
    words: Optional[List[WordBox]] = None
    engine: str = ""
    profile: str = ""


class OcrEngine(Protocol):
    name: str

    def ocr(self, image: Image.Image, *, with_words: bool, profile: str) -> OcrResult:
        ...
