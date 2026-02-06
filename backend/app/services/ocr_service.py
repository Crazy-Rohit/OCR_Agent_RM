import io
import os
import platform
import time
import uuid
from typing import List, Dict, Any

import pytesseract
import pypdfium2 as pdfium
from PIL import Image, ImageOps, ImageFilter
from docx import Document
from pytesseract import Output

from app.models.schemas import OCRResponse, PageText
from app.services import file_service
from app.core.config import settings

from app.services.ocr_phase2_adapter import phase2_enrich_page
from app.services.semantic_cleanup import cleanup_page
from app.services.quality_scoring import score_page


def configure_tesseract():
    env_cmd = os.getenv("TESSERACT_CMD")
    if env_cmd and os.path.exists(env_cmd):
        pytesseract.pytesseract.tesseract_cmd = env_cmd
        return

    if platform.system().lower().startswith("win"):
        win_default = r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe"
        if os.path.exists(win_default):
            pytesseract.pytesseract.tesseract_cmd = win_default
            return


configure_tesseract()


def _preprocess(image: Image.Image) -> Image.Image:
    image = image.convert("L")

    w, h = image.size
    max_side = max(w, h)
    if max_side < 1000:
        scale = 1000 / max_side
        image = image.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    image = ImageOps.autocontrast(image)
    image = image.filter(ImageFilter.SHARPEN)
    return image


def ocr_image_words(image: Image.Image) -> Dict[str, Any]:
    """OCR with word-level confidence + bbox."""
    image = _preprocess(image)
    data = pytesseract.image_to_data(image, output_type=Output.DICT)

    words: List[Dict[str, Any]] = []
    texts: List[str] = []

    n = len(data.get("text", []))
    for i in range(n):
        txt = (data["text"][i] or "").strip()
        conf = data["conf"][i]

        # Keep only non-empty tokens; NO confidence-based dropping
        if not txt:
            continue

        try:
            # Tesseract conf is 0..100; normalize to 0..1; -1 means "no conf"
            conf_i = float(conf)
            conf_f = conf_i / 100.0 if conf_i >= 0 else None
        except Exception:
            conf_f = None

        left = int(data["left"][i])
        top = int(data["top"][i])
        width = int(data["width"][i])
        height = int(data["height"][i])

        words.append(
            {
                "text": txt,
                "confidence": conf_f,
                "bbox": [left, top, left + width, top + height],
            }
        )
        texts.append(txt)

    return {"text": " ".join(texts).strip(), "words": words}


def extract_from_pdf(file_bytes: bytes) -> List[PageText]:
    pdf = pdfium.PdfDocument(file_bytes)
    pages: List[PageText] = []

    for i in range(len(pdf)):
        page = pdf[i]

        text = ""
        try:
            textpage = page.get_textpage()
            text = (textpage.get_text_range() or "").strip()
        except Exception:
            text = ""

        if text:
            pages.append(PageText(page_number=i + 1, text=text))
        else:
            scale = 300 / 72.0
            bitmap = page.render(scale=scale)
            pil_image = bitmap.to_pil()

            o = ocr_image_words(pil_image)
            pages.append(PageText(page_number=i + 1, text=o["text"], words=o["words"]))

    return pages


def extract_from_image(file_bytes: bytes) -> List[PageText]:
    image = Image.open(io.BytesIO(file_bytes))
    o = ocr_image_words(image)
    return [PageText(page_number=1, text=o["text"], words=o["words"])]


def extract_from_docx(file_bytes: bytes) -> List[PageText]:
    doc = Document(io.BytesIO(file_bytes))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    text = "\n".join(paragraphs)
    return [PageText(page_number=1, text=text)]


def process_file(
    file_bytes: bytes,
    filename: str,
    document_type: str,
    *,
    zero_retention: bool | None = None,
) -> OCRResponse:
    start = time.time()
    job_id = str(uuid.uuid4())

    if zero_retention is None:
        zero_retention = settings.ZERO_RETENTION_DEFAULT

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext == "pdf":
        pages = extract_from_pdf(file_bytes)
    elif ext in {"jpg", "jpeg", "png", "bmp", "tif", "tiff"}:
        pages = extract_from_image(file_bytes)
    elif ext == "docx":
        pages = extract_from_docx(file_bytes)
    else:
        raise ValueError(f"Unsupported file type: .{ext or 'unknown'}")

    # -------- Phase 2 + Phase 3 (early) --------
    enriched_pages: List[PageText] = []
    page_quality: List[Dict[str, Any]] = []

    for p in pages:
        page_dict = p.model_dump() if hasattr(p, "model_dump") else p.dict()

        # Phase 2: layout reconstruction
        page_dict = phase2_enrich_page(page_dict)

        # Phase 3 early: semantic cleanup + quality scoring
        page_dict = cleanup_page(page_dict)
        page_dict["quality"] = score_page(page_dict.get("words") or [], page_dict.get("text_normalized") or page_dict.get("text") or "")

        page_quality.append({"page": page_dict.get("page_number"), **(page_dict.get("quality") or {})})
        enriched_pages.append(PageText(**page_dict))

    # Prefer normalized text for full_text if present
    full_text = "\n\n".join((p.text_normalized or p.text or "") for p in enriched_pages).strip()
    processing_time_ms = int((time.time() - start) * 1000)

    if not zero_retention:
        file_service.save_unique_by_name(filename, file_bytes)
    else:
        file_service.delete_if_exists(filename)

    # Aggregate quality
    qs = [q.get("quality_score") for q in page_quality if isinstance(q.get("quality_score"), (int, float))]
    avg_quality = (sum(qs) / len(qs)) if qs else None

    return OCRResponse(
        job_id=job_id,
        status="success",
        document_type=document_type,
        pages=enriched_pages,
        full_text=full_text,
        metadata={
            "file_name": filename,
            "file_type": ext,
            "num_pages": len(enriched_pages),
            "processing_time_ms": processing_time_ms,
            "engine": "tesseract",
            "zero_retention": bool(zero_retention),
            "phase2_complete": True,
            "phase3_started": True,
            "avg_quality_score": avg_quality,
            "page_quality": page_quality,
        },
    )
