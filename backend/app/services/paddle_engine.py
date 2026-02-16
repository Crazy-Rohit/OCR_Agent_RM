from paddleocr import PaddleOCR
import numpy as np
from PIL import Image
import cv2


class PaddleHandwritingEngine:
    def __init__(self):
        # English handwriting optimized
        self.ocr = PaddleOCR(
            use_angle_cls=True,
            lang="en",
            show_log=False
        )

    def extract_text_from_region(self, image: Image.Image, bbox: tuple):
        """
        bbox format: (x1, y1, x2, y2)
        """
        try:
            x1, y1, x2, y2 = bbox
            crop = image.crop((x1, y1, x2, y2))

            # Convert PIL to OpenCV format
            open_cv_image = np.array(crop)
            open_cv_image = cv2.cvtColor(open_cv_image, cv2.COLOR_RGB2BGR)

            result = self.ocr.ocr(open_cv_image)

            if not result or not result[0]:
                return ""

            texts = [line[1][0] for line in result[0]]
            return " ".join(texts)

        except Exception as e:
            print("Paddle OCR error:", str(e))
            return ""
