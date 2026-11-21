"""Classify an orange from a photo someone sends to the bot.

Runs the same colour check as the web scanner (peel.py), on the laptop. The photo is never
sent anywhere else. Only the centre of the picture is analysed, so the orange should fill it.
"""
from __future__ import annotations

import io
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageOps

from .peel import classify_rgb, confidence_level

Image.MAX_IMAGE_PIXELS = 25_000_000

ANALYSIS_SIZE = 128  # pixels per side of the analysed square, like the browser's downsampling
CENTRE_SHARE = 0.7  # share of the photo's short side that is analysed

TITLE = {"unripe": "Unripe", "ripening": "Ripening", "ripe": "Ready to pick",
         "mold": "Possible mold", "none": "No orange found"}
ADVICE = {
    "unripe": "Mostly green peel. Leave it on the tree.",
    "ripening": "Green turning orange. Check it again in a few days.",
    "ripe": "Even, deep orange peel. It's ready to pick.",
    "mold": "I see white fuzz or blue-green patches. Remove it before the mold spreads.",
    "none": "I can't find an orange in the middle of the photo. Try again with the orange filling the centre, in daylight.",
}


@dataclass(frozen=True)
class PhotoResult:
    label: str  # unripe | ripening | ripe | mold | none
    confidence: str  # high | medium | low
    scores: dict


def centre_square(image: Image.Image) -> np.ndarray:
    """The central square of the photo, downsampled, as an RGB float array."""
    image.draft("RGB", (512, 512))
    image = ImageOps.exif_transpose(image).convert("RGB")
    w, h = image.size
    side = int(min(w, h) * CENTRE_SHARE)
    left, top = (w - side) // 2, (h - side) // 2
    square = image.crop((left, top, left + side, top + side)).resize((ANALYSIS_SIZE, ANALYSIS_SIZE),
                                                                    Image.Resampling.BILINEAR)
    return np.asarray(square, dtype=np.float64)


def classify_photo(data: bytes) -> PhotoResult:
    with Image.open(io.BytesIO(data)) as image:
        if image.width * image.height > Image.MAX_IMAGE_PIXELS:
            raise Image.DecompressionBombError("Photo exceeds the pixel limit")
        rgb = centre_square(image)
    result = classify_rgb(rgb)
    label = result["label"]
    return PhotoResult(label, confidence_level(result["confidence"]), result["scores"])


def photo_reply(result: PhotoResult) -> str:
    if result.label == "none":
        return ADVICE["none"]
    return (f"{TITLE[result.label]} ({result.confidence} confidence). {ADVICE[result.label]}\n"
            "This is a colour check of the centre of your photo, a stand-in until the trained model is ready.")
