#!/usr/bin/env python3
"""Server-side OCR af Bambu Lab farve-labels – finder 5-cifret farve-ID."""

from __future__ import annotations

import io
import re
import sys

from PIL import Image, ImageEnhance, ImageOps

try:
    import pillow_heif

    pillow_heif.register_heif_opener()
except ImportError:
    pass

MAX_DIM = 1600
_COLOR_ID_RE = re.compile(r'[1-9]\d{4}')


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


def normalize_text(text: str) -> str:
    return (
        text.replace('（', '(')
        .replace('）', ')')
        .replace('０', '0')
        .replace('１', '1')
        .replace('２', '2')
        .replace('３', '3')
        .replace('４', '4')
        .replace('５', '5')
        .replace('６', '6')
        .replace('７', '7')
        .replace('８', '8')
        .replace('９', '9')
        .replace('O', '0')
        .replace('o', '0')
        .replace('l', '1')
        .replace('I', '1')
    )


def extract_color_ids(text: str) -> list[str]:
    text = normalize_text(text)
    ids: list[str] = []
    seen: set[str] = set()

    def add(value: str) -> None:
        code = value.strip()
        if not _COLOR_ID_RE.fullmatch(code) or code in seen:
            return
        seen.add(code)
        ids.append(code)

    for match in re.finditer(r'\((\d{5})\)', text):
        add(match.group(1))
    for match in re.finditer(r'(?:ID|id|SKU|sku|No|Nr)[.: ]*(\d{5})', text, flags=re.I):
        add(match.group(1))
    for match in re.finditer(r'\b([1-9]\d{4})\b', text):
        add(match.group(1))

    return ids


def image_variants(img: Image.Image) -> list[Image.Image]:
    img = resize_image(img)
    gray = ImageOps.grayscale(img)
    return [
        img,
        ImageOps.autocontrast(gray).convert('RGB'),
        ImageEnhance.Contrast(gray).enhance(2.0).convert('RGB'),
        ImageEnhance.Sharpness(gray).enhance(2.0).convert('RGB'),
    ]


def to_jpeg_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=88)
    return buf.getvalue()


_OCR_ENGINE = None


def get_ocr_engine():
    global _OCR_ENGINE
    if _OCR_ENGINE is None:
        from rapidocr_onnxruntime import RapidOCR

        _OCR_ENGINE = RapidOCR()
    return _OCR_ENGINE


def run_ocr(ocr, data: bytes) -> str:
    result, _ = ocr(data)
    if not result:
        return ''
    parts = [str(item[1]).strip() for item in result if len(item) > 1 and item[1]]
    return '\n'.join(parts)


def ocr_image_bytes(data: bytes) -> dict:
    img = open_image(data)
    ocr = get_ocr_engine()
    all_text: list[str] = []
    all_ids: list[str] = []
    seen_ids: set[str] = set()

    for variant in image_variants(img):
        text = run_ocr(ocr, to_jpeg_bytes(variant))
        if text:
            all_text.append(text)
        for color_id in extract_color_ids(text):
            if color_id not in seen_ids:
                seen_ids.add(color_id)
                all_ids.append(color_id)
        if all_ids:
            break

    if not all_ids:
        raise ValueError(
            'Ingen farve-ID fundet på label. Tag et tydeligt billede af teksten «(10100)».'
        )

    return {'text': '\n'.join(all_text), 'ids': all_ids}


def main() -> int:
    data = sys.stdin.buffer.read()
    try:
        import json

        print(json.dumps(ocr_image_bytes(data), ensure_ascii=False))
        return 0
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        print(f'OCR fejl: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
