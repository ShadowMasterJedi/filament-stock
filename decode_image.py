#!/usr/bin/env python3
"""Server-side stregkode-læsning fra billeder med zxing-cpp."""

from __future__ import annotations

import io
import sys

import numpy as np
import zxingcpp
from PIL import Image, ImageEnhance, ImageOps

try:
    import pillow_heif

    pillow_heif.register_heif_opener()
except ImportError:
    pass

MAX_DIM = 1600


def open_image(data: bytes) -> Image.Image:
    if not data:
        raise ValueError('Tom fil')
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
        return img.convert('RGB')
    except Exception as exc:
        raise ValueError(f'Kunne ikke åbne billedet: {exc}') from exc


def resize_image(img: Image.Image) -> Image.Image:
    w, h = img.size
    longest = max(w, h)
    if longest <= MAX_DIM:
        return img
    scale = MAX_DIM / longest
    return img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)


def to_array(img: Image.Image) -> np.ndarray:
    return np.array(img.convert('RGB'))


def try_decode(arr: np.ndarray) -> str | None:
    results = zxingcpp.read_barcodes(arr)
    for result in results:
        text = (result.text or '').strip()
        if text:
            return text
    return None


def variants(img: Image.Image) -> list[np.ndarray]:
    """Begrænset sæt forsøg – hurtigt nok til mobil-upload."""
    img = resize_image(img)
    w, h = img.size
    if w < 1 or h < 1:
        return []

    gray = ImageOps.grayscale(img)
    bases = [
        img,
        ImageOps.autocontrast(gray).convert('RGB'),
        ImageEnhance.Contrast(gray).enhance(1.8).convert('RGB'),
    ]

    out: list[np.ndarray] = []
    for base in bases:
        out.append(to_array(base))
        for scale in (1.5, 2.0):
            nw = max(1, int(w * scale))
            nh = max(1, int(h * scale))
            if max(nw, nh) > 2400:
                continue
            scaled = base.resize((nw, nh), Image.Resampling.LANCZOS)
            out.append(to_array(scaled))
        for angle in (90, 180):
            rotated = base.rotate(angle, expand=True)
            out.append(to_array(rotated))

    return out


def decode_image_bytes(data: bytes) -> str:
    img = open_image(data)
    for arr in variants(img):
        text = try_decode(arr)
        if text:
            return text
    raise ValueError(
        'Ingen stregkode fundet. Tag billedet tættere på stregkoden, '
        'med god belysning og uden refleksioner.'
    )


def main() -> int:
    data = sys.stdin.buffer.read()
    try:
        print(decode_image_bytes(data))
        return 0
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
