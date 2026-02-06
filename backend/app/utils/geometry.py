def sort_boxes_reading_order(boxes):
    return sorted(boxes, key=lambda b: (b["bbox"][1], b["bbox"][0]))

def merge_boxes(boxes):
    x1 = min(b["bbox"][0] for b in boxes)
    y1 = min(b["bbox"][1] for b in boxes)
    x2 = max(b["bbox"][2] for b in boxes)
    y2 = max(b["bbox"][3] for b in boxes)
    return [x1, y1, x2, y2]