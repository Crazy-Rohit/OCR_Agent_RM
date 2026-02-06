from typing import List, Dict

def build_layout(words: List[Dict]) -> Dict:
    """Group words into lines and blocks using simple y/x heuristics."""
    lines = []
    current_line = []
    last_y = None

    for w in sorted(words, key=lambda x: (x["bbox"][1], x["bbox"][0])):
        y = w["bbox"][1]
        if last_y is None or abs(y - last_y) < 10:
            current_line.append(w)
        else:
            lines.append(current_line)
            current_line = [w]
        last_y = y

    if current_line:
        lines.append(current_line)

    blocks = [{"lines": line} for line in lines]

    return {
        "lines": lines,
        "blocks": blocks
    }