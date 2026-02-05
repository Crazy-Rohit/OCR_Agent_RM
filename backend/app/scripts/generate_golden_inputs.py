from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
GOLDEN_DIR = ROOT / "tests" / "golden_inputs"


def _load_font(size: int = 40) -> ImageFont.ImageFont:
    """Try to load a reasonable truetype font; fall back to default."""
    for name in [
        "DejaVuSans.ttf",
        "arial.ttf",
        "Arial.ttf",
    ]:
        try:
            return ImageFont.truetype(name, size=size)
        except Exception:
            continue
    return ImageFont.load_default()


def make_test_image(text: str, *, w: int = 1400, h: int = 400) -> Image.Image:
    img = Image.new("RGB", (w, h), "white")
    draw = ImageDraw.Draw(img)
    font = _load_font(52)
    draw.text((60, 120), text, fill="black", font=font)
    return img


def main() -> None:
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)

    # 1) Simple printed text image
    img1 = make_test_image("HELLO OCR AGENT V0")
    img_path = GOLDEN_DIR / "hello_v0.png"
    img1.save(img_path)

    # 2) Same content as a PDF (Pillow can write PDF)
    pdf_path = GOLDEN_DIR / "hello_v0.pdf"
    img1.save(pdf_path, "PDF", resolution=300.0)

    # 3) Rotated image
    rot = img1.rotate(7, expand=True, fillcolor="white")
    rot_path = GOLDEN_DIR / "hello_v0_rotated.png"
    rot.save(rot_path)

    print(f"✅ Generated golden inputs in: {GOLDEN_DIR}")
    for p in [img_path, pdf_path, rot_path]:
        print(f" - {p.name}")


if __name__ == "__main__":
    main()
