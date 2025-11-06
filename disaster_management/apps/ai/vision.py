# vision.py
from PIL import Image
import io

def image_evidence_score(file_obj, hazard: str) -> float:
    """
    Start simple: if flood → look for large blue-ish regions; fire → red/orange dominance.
    Replace with EfficientNet later.
    """
    try:
        im = Image.open(file_obj).convert("RGB").resize((256, 256))
        px = list(im.getdata())
    except Exception:
        return 0.2

    r = sum(p[0] for p in px) / (255 * len(px))
    g = sum(p[1] for p in px) / (255 * len(px))
    b = sum(p[2] for p in px) / (255 * len(px))

    if hazard == "flood":
        # more blue than red/green → water-ish
        score = max(0.0, b - max(r, g))
    elif hazard == "fire":
        # strong red dominance → fire-ish
        score = max(0.0, r - max(g, b))
    else:
        score = (r + g + b) / 3.0 * 0.2
    return float(min(1.0, score * 1.8))
