#!/usr/bin/env python3
"""Hent Bambu Lab filament-katalog fra eu.store.bambulab.com."""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SEED_PATH = ROOT / 'data' / 'bambu_barcode_seed.json'
HANDLES_PATH = ROOT / 'data' / 'bambu_handles.json'
CACHE_PATH = ROOT / 'data' / 'bambu_catalog_cache.json'
STORE_BASE = 'https://eu.store.bambulab.com'
COLLECTION_URL = f'{STORE_BASE}/en/collections/bambu-lab-3d-printer-filament'
USER_AGENT = 'FilamentStock/1.0 (+local inventory sync)'

VARIANT_NAME_RE = re.compile(
    r'"name":\s*"(?P<line>[^"]+?)\s*-\s*(?P<color>[^"(]+?)\s*\((?P<code>\d{5})\)\s*/\s*(?P<spool>[^/]+?)\s*/\s*(?P<weight>[^"]+)"'
)
VARIANT_SKU_RE = re.compile(r'"sku":\s*"(?P<sku>\d+)"')
PRODUCT_LINK_RE = re.compile(r'/en/products/[a-z0-9-]+')
PRODUCT_GROUP_NAME_RE = re.compile(r'"@type":\s*"ProductGroup"[\s\S]*?"name":\s*"(?P<name>[^"]+)"')
CHUNK_RE = re.compile(r'self\.__next_f\.push\(\[1,"((?:\\.|[^"\\])*)"\]\)')


def fetch(url: str, timeout: int = 30, retries: int = 4) -> str:
    last_err: Exception | None = None
    for attempt in range(retries):
        req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode('utf-8', errors='replace')
        except urllib.error.HTTPError as exc:
            last_err = exc
            if exc.code == 429 and attempt < retries - 1:
                time.sleep(3.0 * (attempt + 1))
                continue
            raise
        except urllib.error.URLError as exc:
            last_err = exc
            if attempt < retries - 1:
                time.sleep(1.0)
                continue
            raise
    if last_err:
        raise last_err
    raise RuntimeError('fetch failed')


def decode_chunks(html: str) -> str:
    chunks = CHUNK_RE.findall(html)
    parts: list[str] = []
    for chunk in chunks:
        try:
            parts.append(chunk.encode('utf-8').decode('unicode_escape'))
        except UnicodeDecodeError:
            parts.append(chunk)
    return '\n'.join(parts)


def infer_material(product_line: str) -> str:
    upper = product_line.upper().replace('  ', ' ')
    rules = [
        ('PLA-CF', 'PLA-CF'),
        ('PETG-CF', 'PETG-CF'),
        ('PET-CF', 'PETG-CF'),
        ('PA6-CF', 'PA-CF'),
        ('PAHT-CF', 'PA-CF'),
        ('PPA-CF', 'PA-CF'),
        ('PPS-CF', 'PA-CF'),
        ('ASA-CF', 'ASA'),
        ('ABS-GF', 'ABS'),
        ('PA6-GF', 'NYLON'),
        ('PLA AERO', 'PLA'),
        ('PLA TOUGH', 'PLA'),
        ('PLA SILK', 'PLA'),
        ('PLA MATTE', 'PLA'),
        ('PLA BASIC', 'PLA'),
        ('PLA ', 'PLA'),
        ('PETG', 'PETG'),
        ('ABS', 'ABS'),
        ('ASA', 'ASA'),
        ('TPU', 'TPU'),
        ('PC FR', 'PC'),
        ('PC', 'PC'),
        ('NYLON', 'NYLON'),
        ('PA6', 'NYLON'),
        ('PAHT', 'NYLON'),
    ]
    for needle, material in rules:
        if needle in upper:
            return material
    return 'Andet'


def parse_weight_g(weight: str) -> int:
    m = re.search(r'(\d+)\s*g', weight, re.I)
    if m:
        return int(m.group(1))
    m = re.search(r'(\d+)\s*kg', weight, re.I)
    if m:
        return int(float(m.group(1)) * 1000)
    return 1000


def parse_product_page(html: str, handle: str) -> list[dict]:
    text = decode_chunks(html)
    group = PRODUCT_GROUP_NAME_RE.search(text)
    default_line = group.group('name').strip() if group else handle.replace('-', ' ').title()

    names = list(VARIANT_NAME_RE.finditer(text))
    skus = [m.group('sku') for m in VARIANT_SKU_RE.finditer(text)]
    if not names or not skus:
        return []

    # JSON-LD variant list: first N sku entries belong to product variants.
    count = len(names)
    variant_skus = skus[:count]
    if len(variant_skus) < count:
        return []

    image_urls = re.findall(
        r'"image":\s*"(https://store\.bblcdn\.eu/[^"]+)"',
        text,
    )

    rows: list[dict] = []
    for idx, match in enumerate(names):
        line = match.group('line').strip() or default_line
        color = match.group('color').strip()
        code = match.group('code')
        spool = match.group('spool').strip()
        weight = match.group('weight').strip()
        store_sku = variant_skus[idx]
        image_url = image_urls[idx] if idx < len(image_urls) else ''
        rows.append(
            {
                'bambu_code': code,
                'store_sku': store_sku,
                'product_line': line,
                'material': infer_material(line),
                'color': color,
                'spool_type': spool,
                'weight_g': parse_weight_g(weight),
                'image_url': image_url,
                'store_url': f'{STORE_BASE}/en/products/{handle}?id={store_sku}',
                'brand': 'Bambu Lab',
            }
        )
    return rows


def load_fallback_handles() -> list[str]:
    if HANDLES_PATH.exists():
        return json.loads(HANDLES_PATH.read_text(encoding='utf-8'))
    return []


def list_product_handles() -> list[str]:
    try:
        html = fetch(COLLECTION_URL)
        handles = sorted({m.group(0).split('/')[-1] for m in PRODUCT_LINK_RE.finditer(html)})
        if handles:
            HANDLES_PATH.write_text(json.dumps(handles, indent=2), encoding='utf-8')
            return handles
    except (urllib.error.URLError, urllib.error.HTTPError):
        pass
    return load_fallback_handles()


def save_catalog_cache(rows: list[dict]) -> None:
    CACHE_PATH.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')


def load_catalog_cache() -> list[dict]:
    if not CACHE_PATH.exists():
        return []
    return json.loads(CACHE_PATH.read_text(encoding='utf-8'))


def load_barcode_seed() -> dict[str, str]:
    if not SEED_PATH.exists():
        return {}
    data = json.loads(SEED_PATH.read_text(encoding='utf-8'))
    mapping: dict[str, str] = {}
    for row in data.get('barcodes', []):
        barcode = str(row.get('barcode', '')).strip()
        key = str(row.get('key', '')).strip()
        if barcode and key:
            mapping[barcode] = key
    return mapping


def seed_key(row: dict) -> str:
    return f"{row['bambu_code']}|{row['spool_type']}"


def apply_barcode_seed(rows: list[dict], seed: dict[str, str]) -> None:
    key_to_barcode = {}
    for barcode, key in seed.items():
        key_to_barcode.setdefault(key, barcode)
    for row in rows:
        row['barcode'] = key_to_barcode.get(seed_key(row), '')


def sync_catalog(verbose: bool = True) -> list[dict]:
    import db

    db.init_db()
    handles = list_product_handles()
    priority = ['pla-basic-filament', 'pla-matte', 'petg-basic', 'petg-hf', 'abs-filament']
    handles = priority + [h for h in handles if h not in priority]
    all_rows: list[dict] = []
    seed = load_barcode_seed()

    if verbose:
        print(f'Fundet {len(handles)} produkter på Bambu Lab EU store…')

    for index, handle in enumerate(handles):
        url = f'{STORE_BASE}/en/products/{handle}'
        try:
            html = fetch(url)
        except (urllib.error.URLError, urllib.error.HTTPError) as exc:
            if verbose:
                print(f'  ✗ {handle}: {exc}', file=sys.stderr)
            continue
        rows = parse_product_page(html, handle)
        apply_barcode_seed(rows, seed)
        all_rows.extend(rows)
        if verbose:
            print(f'  ✓ {handle}: {len(rows)} varianter')
        if index < len(handles) - 1:
            time.sleep(1.5)

    if not all_rows:
        cached = load_catalog_cache()
        if cached:
            apply_barcode_seed(cached, seed)
            all_rows = cached
            if verbose:
                print('Bruger cached Bambu-katalog (webshop rate-limit)', file=sys.stderr)
        else:
            raise RuntimeError('Ingen Bambu data hentet – prøv igen om lidt')

    save_catalog_cache(all_rows)
    db.replace_bambu_catalog(all_rows)
    if verbose:
        with_barcode = sum(1 for r in all_rows if r.get('barcode'))
        print(f'Gemt {len(all_rows)} Bambu varianter ({with_barcode} med stregkode fra seed)')
    return all_rows


def main() -> int:
    try:
        sync_catalog(verbose=True)
        return 0
    except Exception as exc:
        print(f'Fejl: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
