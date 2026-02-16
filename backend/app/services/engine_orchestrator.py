from paddleocr import PaddleOCR
from PIL import Image
import numpy as np
import cv2


class EngineOrchestrator:

    def __init__(self):
        self.ocr = PaddleOCR(
            use_angle_cls=True,
            lang="en",
            show_log=False
        )

    def process_document(self, document_model, image: Image.Image):
        """
        Full-page PaddleOCR.
        No routing. No block detection before OCR.
        Paddle gives us text + bbox.
        """

        open_cv_image = np.array(image)
        open_cv_image = cv2.cvtColor(open_cv_image, cv2.COLOR_RGB2BGR)

        result = self.ocr.ocr(open_cv_image)

        blocks = []

        if result and result[0]:
            for line in result[0]:
                bbox_points = line[0]
                text = line[1][0]
                confidence = float(line[1][1])

                x_coords = [p[0] for p in bbox_points]
                y_coords = [p[1] for p in bbox_points]

                block = {
                    "text": text,
                    "confidence": confidence,
                    "bbox": {
                        "x1": int(min(x_coords)),
                        "y1": int(min(y_coords)),
                        "x2": int(max(x_coords)),
                        "y2": int(max(y_coords)),
                    },
                    "engine": "paddle"
                }

                blocks.append(block)

        # Replace existing blocks
        for page in document_model.pages:
            page.blocks = blocks
            page.engine_usage = {
                "primary_engine": "paddleocr",
                "handwriting_supported": True
            }

        return document_model
