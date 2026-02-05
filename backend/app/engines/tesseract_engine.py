from __future__ import annotations

import os
import platform
from typing import List, Optional

import pytesseract
from pytesseract import Output
from PIL import Image

from app.engines.base import OcrResult
from app.models.schemas import WordBox


def configure_tesseract() -> None:
    env_cmd = os.getenv("TESSERACT_CMD")
    if env_cmd and os.path.exists(env_cmd):
        pytesseract.pytesseract.tesseract_cmd = env_cmd
        return

    if platform.system().lower().startswith("win"):
        win_default = r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe"
        if os.path.exists(win_default):
            pytesseract.pytesseract.tesseract_cmd = win_default


configure_tesseract()


class TesseractEngine:
    name = "tesseract"

    # Profiles can be tuned later; keep simple in V1
    _profiles = {
        "printed": "--oem 1 --psm 6",
        "scanned": "--oem 1 --psm 6",
        "handwriting_hint": "--oem 1 --psm 6",
    }

    def _config_for_profile(self, profile: str) -> str:
        return self._profiles.get(profile, "--oem 1 --psm 6")

    def ocr(self, image: Image.Image, *, with_words: bool, profile: str) -> OcrResult:
        config = self._config_for_profile(profile)

        if not with_words:
            text = pytesseract.image_to_string(image, config=config)
            return OcrResult(text=(text or "").strip(), words=None, engine=self.name, profile=profile)

        data = pytesseract.image_to_data(image, config=config, output_type=Output.DICT)
        words: List[WordBox] = []

        n = len(data.get("text", []))
        for i in range(n):
            txt = (data["text"][i] or "").strip()
            if not txt:
                continue

            conf: Optional[float] = None
            try:
                conf_raw = data["conf"][i]
                if conf_raw not in (None, "", "-1"):
                    conf = float(conf_raw)
            except Exception:
                conf = None

            x = int(data["left"][i])
            y = int(data["top"][i])
            w = int(data["width"][i])
            h = int(data["height"][i])

            words.append(WordBox(text=txt, x1=x, y1=y, x2=x + w, y2=y + h, confidence=conf))

        text = pytesseract.image_to_string(image, config=config)
        return OcrResult(text=(text or "").strip(), words=words, engine=self.name, profile=profile)
