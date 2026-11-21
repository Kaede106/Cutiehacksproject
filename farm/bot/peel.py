"""Colour heuristic: a numpy port of the browser scanner's classifier.

Source of truth: web/src/scanner/classifier.js (THRESHOLDS, classifyPixel, analyzeBuffer,
scoreAnalysis, confidenceLevel). This file mirrors it function by function so the browser demo
and the bot give the same answer on the same pixels. If you retune THRESHOLDS in the JS,
copy the numbers here.

Everything here works on RGB float arrays in 0..255, the same values the JS sees in its RGBA
buffer. Convert OpenCV's BGR with `bgr[..., ::-1]` before calling.
"""
from __future__ import annotations

import numpy as np

LABELS = ("unripe", "ripening", "ripe", "mold")

# Copied from THRESHOLDS in web/src/scanner/classifier.js. Keep the two in step.
THRESHOLDS = {
    "darkV": 0.2,  # darker pixels are shadow or background
    "glare": {"minV": 0.965, "maxS": 0.12},  # clipped specular highlights, never counted as mold
    "fruit": {"minS": 0.33, "minV": 0.22, "hueMin": 5, "hueMax": 145},
    "white": {"maxS": 0.2, "minV": 0.62},  # white fuzz
    "blueGreen": {"hueMin": 150, "hueMax": 235, "minS": 0.1, "maxS": 0.65, "minV": 0.25, "maxV": 0.92},
    # YCbCr box for skin (and brown wood). Saturated orange peel has Cb < 77, so it falls outside.
    "skin": {"cbMin": 77, "cbMax": 127, "crMin": 133, "crMax": 173, "maxS": 0.72, "maxHue": 50},
    # Hue breakpoints in degrees: orange up to ripeFull, yellow between yellowFull and yellowEnd,
    # green from greenFull. Linear blends between them, so the three weights always sum to 1.
    "hue": {"ripeFull": 36, "yellowFull": 48, "yellowEnd": 60, "greenFull": 76},
    "coverage": {"none": 0.1, "full": 0.4},  # share of the region that must be fruit
    "grid": 16,  # the region is split into grid x grid cells for the mold search
    "fruitCell": 0.35,
    "moldCell": 0.25,
    "enclosureRays": 5,  # of 8 rays from a mold cell, this many must reach fruit
    "mold": {"evidenceStart": 0.03, "evidenceFull": 0.1, "blueWeight": 2.5},
}

# Pixel classes, same numbering as PIXEL_CLASS in the JS.
DARK, GLARE, WHITE, BLUE, FRUIT, SKIN, OTHER = range(7)

_RAYS = ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1))


def rgb_to_hsv(rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Hue in degrees 0..360, saturation and value in 0..1. Mirrors rgbToHsv() in the JS.

    OpenCV's own HSV (hue 0..180, rounded to uint8) is deliberately not used: it would shift
    pixels across the thresholds and the two runners would disagree.
    """
    rgb = np.asarray(rgb, dtype=np.float64)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    d = mx - mn
    has = d > 0
    safe = np.where(has, d, 1.0)
    # Same tie order as the JS: red wins over green, green over blue.
    is_r = has & (mx == r)
    is_g = has & ~is_r & (mx == g)
    is_b = has & ~is_r & ~is_g
    h = np.zeros_like(mx)
    h = np.where(is_r, np.fmod((g - b) / safe, 6), h)
    h = np.where(is_g, (b - r) / safe + 2, h)
    h = np.where(is_b, (r - g) / safe + 4, h)
    h = h * 60
    h = np.where(h < 0, h + 360, h)
    s = np.where(mx > 0, d / np.where(mx > 0, mx, 1.0), 0.0)
    return h, s, mx / 255


def is_skin_tone(rgb: np.ndarray, T: dict = THRESHOLDS) -> np.ndarray:
    rgb = np.asarray(rgb, dtype=np.float64)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    cb = 128 - 0.168736 * r - 0.331264 * g + 0.5 * b
    cr = 128 + 0.5 * r - 0.418688 * g - 0.081312 * b
    k = T["skin"]
    return (cb >= k["cbMin"]) & (cb <= k["cbMax"]) & (cr >= k["crMin"]) & (cr <= k["crMax"])


def classify_pixels(rgb: np.ndarray, T: dict = THRESHOLDS) -> tuple[np.ndarray, np.ndarray]:
    """Class of every pixel (DARK..OTHER) and its hue. Mirrors classifyPixel() in the JS."""
    h, s, v = rgb_to_hsv(rgb)
    bg, f, k = T["blueGreen"], T["fruit"], T["skin"]
    dark = v < T["darkV"]
    glare = (v > T["glare"]["minV"]) & (s < T["glare"]["maxS"])
    white = (s <= T["white"]["maxS"]) & (v >= T["white"]["minV"])
    blue = (h >= bg["hueMin"]) & (h <= bg["hueMax"]) & (s >= bg["minS"]) & (s <= bg["maxS"]) \
        & (v >= bg["minV"]) & (v <= bg["maxV"])
    fruitish = (h >= f["hueMin"]) & (h <= f["hueMax"]) & (s >= f["minS"]) & (v >= f["minV"])
    skin = fruitish & (h < k["maxHue"]) & (s < k["maxS"]) & is_skin_tone(rgb, T)
    # np.select takes the first true condition, which keeps the JS's if/else order.
    cls = np.select(
        [dark, glare, white, blue, skin, fruitish],
        [DARK, GLARE, WHITE, BLUE, SKIN, FRUIT],
        default=OTHER,
    ).astype(np.uint8)
    return cls, h


def hue_weights(h: np.ndarray, T: dict = THRESHOLDS) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Split fruit hues into (ripe, yellow, green) weights that sum to 1. Mirrors hueWeights()."""
    t = T["hue"]
    rf, yf, ye, gf = t["ripeFull"], t["yellowFull"], t["yellowEnd"], t["greenFull"]
    h = np.asarray(h, dtype=np.float64)
    up = (h - rf) / (yf - rf)
    down = (h - ye) / (gf - ye)
    ripe = np.where(h <= rf, 1.0, np.where(h < yf, 1 - up, 0.0))
    yellow = np.where(h <= rf, 0.0, np.where(h < yf, up, np.where(h <= ye, 1.0, np.where(h < gf, 1 - down, 0.0))))
    green = np.where(h <= ye, 0.0, np.where(h < gf, down, 1.0))
    return ripe, yellow, green


def _clamp01(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def smoothstep(a: float, b: float, x: float) -> float:
    t = _clamp01((x - a) / (b - a))
    return t * t * (3 - 2 * t)


def analyze(rgb: np.ndarray, T: dict = THRESHOLDS) -> dict:
    """Count pixel classes and find mold cells enclosed by fruit. Mirrors analyzeBuffer()."""
    height, width = rgb.shape[:2]
    gw = max(1, min(T["grid"], width))
    gh = max(1, min(T["grid"], height))
    cells = gw * gh
    cls, hue = classify_pixels(rgb, T)

    rows = (np.arange(height) * gh) // height
    cols = (np.arange(width) * gw) // width
    cell = (rows[:, None] * gw + cols[None, :]).ravel()
    flat = cls.ravel()

    def per_cell(which: int) -> np.ndarray:
        return np.bincount(cell[flat == which], minlength=cells)

    c_total = np.bincount(cell, minlength=cells)
    c_fruit, c_white, c_blue = per_cell(FRUIT), per_cell(WHITE), per_cell(BLUE)
    counts = np.bincount(flat, minlength=7)
    w_ripe, w_yellow, w_green = (float(w.sum()) for w in hue_weights(hue.ravel()[flat == FRUIT], T))

    with np.errstate(invalid="ignore", divide="ignore"):
        has = c_total > 0
        fruit_cell = has & (c_fruit / np.where(has, c_total, 1) >= T["fruitCell"])
        mold_cand = has & ((c_white + c_blue) / np.where(has, c_total, 1) >= T["moldCell"])

    # A mold candidate counts only when fruit surrounds it: cast 8 rays through other candidate
    # cells and require most of them to reach a fruit cell. A white wall or table next to the
    # fruit reaches fruit in at most three or four directions, so it is ignored.
    enclosed = np.zeros(cells, dtype=bool)
    for cy in range(gh):
        for cx in range(gw):
            c = cy * gw + cx
            if not mold_cand[c]:
                continue
            hits = 0
            for dx, dy in _RAYS:
                x, y = cx + dx, cy + dy
                while 0 <= x < gw and 0 <= y < gh:
                    n = y * gw + x
                    if fruit_cell[n]:
                        hits += 1
                        break
                    if not mold_cand[n]:
                        break
                    x += dx
                    y += dy
            if hits >= T["enclosureRays"]:
                enclosed[c] = True

    return {
        "width": width, "height": height, "gw": gw, "gh": gh,
        "total": width * height,
        "fruit": int(counts[FRUIT]),
        "skin": int(counts[SKIN]),
        "glare": int(counts[GLARE]),
        "dark": int(counts[DARK]),
        "weights": {"ripe": w_ripe, "yellow": w_yellow, "green": w_green},
        "moldWhite": int(c_white[enclosed].sum()),
        "moldBlue": int(c_blue[enclosed].sum()),
        "enclosed": enclosed,
    }


def _mold_regions(stats: dict) -> list[dict]:
    """Connected groups of enclosed mold cells as 0..1 boxes. Mirrors moldRegions()."""
    enclosed, gw, gh = stats["enclosed"], stats["gw"], stats["gh"]
    seen = np.zeros(len(enclosed), dtype=bool)
    regions = []
    for start in range(len(enclosed)):
        if not enclosed[start] or seen[start]:
            continue
        min_x, min_y, max_x, max_y, size = gw, gh, -1, -1, 0
        stack = [start]
        seen[start] = True
        while stack:
            c = stack.pop()
            x, y = c % gw, c // gw
            size += 1
            min_x, max_x, min_y, max_y = min(min_x, x), max(max_x, x), min(min_y, y), max(max_y, y)
            for n in (c - 1 if x > 0 else -1, c + 1 if x < gw - 1 else -1,
                      c - gw if y > 0 else -1, c + gw if y < gh - 1 else -1):
                if n >= 0 and enclosed[n] and not seen[n]:
                    seen[n] = True
                    stack.append(n)
        regions.append({"x": min_x / gw, "y": min_y / gh, "w": (max_x - min_x + 1) / gw,
                        "h": (max_y - min_y + 1) / gh, "label": "mold", "size": size})
    regions.sort(key=lambda r: -r["size"])  # stable, like Array.prototype.sort
    return [{k: v for k, v in r.items() if k != "size"} for r in regions[:4]]


def score(stats: dict, T: dict = THRESHOLDS) -> dict:
    """Turn pixel statistics into a reading. Mirrors scoreAnalysis().

    Returns {label, confidence (0..1), scores, regions, coverage}. label is one of LABELS or
    'none' when fruit covers less than coverage.none of the region.
    """
    mold_area = stats["moldWhite"] + stats["moldBlue"]
    fruit_area = stats["fruit"] + mold_area
    coverage = fruit_area / stats["total"] if stats["total"] else 0.0

    o = y = g = 0.0
    if stats["fruit"]:
        o = stats["weights"]["ripe"] / stats["fruit"]
        y = stats["weights"]["yellow"] / stats["fruit"]
        g = stats["weights"]["green"] / stats["fruit"]
    # Green and orange on the same fruit is the ripening signal, so the smaller of the two
    # shares moves into "ripening" with extra weight.
    mix = min(g, o)
    m = T["mold"]
    evidence = (stats["moldWhite"] + m["blueWeight"] * stats["moldBlue"]) / fruit_area if fruit_area else 0.0
    mold_score = smoothstep(m["evidenceStart"], m["evidenceFull"], evidence)
    keep = 1 - mold_score
    scores = {
        "unripe": (g - 0.75 * mix) * keep,
        "ripening": (y + 1.5 * mix) * keep,
        "ripe": (o - 0.75 * mix) * keep,
        "mold": mold_score if fruit_area else 0.0,
    }

    if coverage < T["coverage"]["none"]:
        return {"label": "none", "confidence": 1 - coverage / T["coverage"]["none"],
                "scores": scores, "regions": [], "coverage": coverage}

    ranked = sorted(LABELS, key=lambda k: -scores[k])  # stable, like the JS sort
    margin = scores[ranked[0]] - scores[ranked[1]]
    coverage_factor = smoothstep(T["coverage"]["none"], T["coverage"]["full"], coverage)
    confidence = coverage_factor * (0.35 + 0.65 * _clamp01(margin / 0.6))
    return {"label": ranked[0], "confidence": confidence, "scores": scores,
            "regions": _mold_regions(stats) if mold_score > 0 else [], "coverage": coverage}


def classify_rgb(rgb: np.ndarray, T: dict = THRESHOLDS) -> dict:
    """classifyBuffer() for an RGB array."""
    return score(analyze(rgb, T), T)


def confidence_level(confidence: float) -> str:
    """Same cut-offs as confidenceLevel() in the JS."""
    if confidence >= 0.7:
        return "high"
    if confidence >= 0.45:
        return "medium"
    return "low"
