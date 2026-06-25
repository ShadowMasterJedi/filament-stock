"""Scrape Bambu Lab filament prices from eu.store.bambulab.com."""

from __future__ import annotations

import re
import time
from typing import Any

from .http_util import fetch

STORE_BASE = 'https://eu.store.bambulab.com'
COLLECTION_URL = f'{STORE_BASE}/en/collections/bambu-lab-3d-printer-filament'

CHUNK_RE = re.compile(r'self\.__next_f\.push\(\[1,"((?:\\.|[^"\\])*)"\]\)')
PRODUCT_LINK_RE = re.compile(r'/en/products/[a-z0-9-]+')
LISTING_RE = re.compile(
    r'"seoCode":"(?P<handle>[a-z0-9-]+)"[^}]*?"name":"(?P<name>[^"]+)"'
    r'[^}]*?"lowerPrice":(?P<lower>\d+\.?\d*)[^}]*?"price":(?P<price>\d+\.?\d*)'
)
VARIANT_NAME_RE = re.compile(
    r'"name":\s*"(?P<line>[^"]+?)\s*-\s*(?P<color>[^"(]+?)\s*\((?P<code>\d{5})\)\s*/\s*'
    r'(?P<spool>[^/]+?)\s*/\s*(?P<weight>[^"]+)"'
)
VARIANT_SKU_RE = re.compile(r'"sku":\s*"(?P<sku>\d+)"')
SKU_PRICE_RE = re.compile(
    r'\{"id":"(?P<sku>\d+)","price":(?P<price>\d+\.\d{2}),"discountPrice":(?P<disc>null|\d+\.\d{2})'
)
PRODUCT_GROUP_NAME_RE = re.compile(r'"@type":\s*"ProductGroup"[\s\S]*?"name":\s*"(?P<name>[^"]+)"')
RSC_LINE_RE = re.compile(r'^([a-z0-9]+):(.*)$')
BULK_MOQ = 10


def _build_rsc_ref_map(text: str) -> dict[str, str]:
    ref_map: dict[str, str] = {}
    for line in text.split('\n'):
        match = RSC_LINE_RE.match(line)
        if match:
            ref_map[match.group(1)] = match.group(2)
    return ref_map


def _resolve_rsc_ref(ref: str, ref_map: dict[str, str], seen: set[str] | None = None) -> Any:
    import json

    seen = seen or set()
    if ref in seen:
        return None
    seen.add(ref)
    val = ref_map.get(ref, '')
    if not val:
        return None
    val = val.strip()
    if val.startswith('"$') and val.endswith('"'):
        return _resolve_rsc_ref(val[2:-1], ref_map, seen)
    if val.startswith('['):
        refs = re.findall(r'\$([a-z0-9]+)', val)
        return [_resolve_rsc_ref(item, ref_map, seen.copy()) for item in refs]
    try:
        return json.loads(val)
    except json.JSONDecodeError:
        return val


def parse_bulk_discounts(text: str) -> dict[str, list[dict[str, float | int]]]:
    """Parse Bambu gradient quantity discounts (4 / 6 / 10 rolls) per SKU."""
    import json

    ref_map = _build_rsc_ref_map(text)
    bulk_by_sku: dict[str, list[dict[str, float | int]]] = {}

    for line in text.split('\n'):
        if '"gradientDiscountSkus"' not in line or '"id":"' not in line:
            continue
        try:
            _, _, payload = line.partition(':')
            sku_obj = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if not isinstance(sku_obj, dict):
            continue
        sku_id = str(sku_obj.get('id', ''))
        gradient_ref = sku_obj.get('gradientDiscountSkus')
        if not sku_id or not isinstance(gradient_ref, str) or not gradient_ref.startswith('$'):
            continue
        tiers_raw = _resolve_rsc_ref(gradient_ref[1:], ref_map)
        if not isinstance(tiers_raw, list):
            continue
        tiers: list[dict[str, float | int]] = []
        for tier in tiers_raw:
            if not isinstance(tier, dict):
                continue
            price = tier.get('gradientDiscountPrice')
            threshold = tier.get('thresholdValue')
            if price is None or threshold is None:
                continue
            tiers.append({
                'threshold': int(threshold),
                'unit_price': round(float(price), 4),
            })
        if tiers:
            bulk_by_sku[sku_id] = sorted(tiers, key=lambda t: t['threshold'])

    return bulk_by_sku


def bulk_tier_at_moq(tiers: list[dict[str, float | int]], moq: int = BULK_MOQ) -> dict[str, float | int] | None:
    eligible = [tier for tier in tiers if tier['threshold'] <= moq]
    if not eligible:
        return None
    return max(eligible, key=lambda tier: tier['threshold'])


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
    return 'Other'


def parse_weight_g(weight: str) -> int:
    m = re.search(r'(\d+)\s*g', weight, re.I)
    if m:
        return int(m.group(1))
    m = re.search(r'(\d+(?:\.\d+)?)\s*kg', weight, re.I)
    if m:
        return int(float(m.group(1)) * 1000)
    return 1000


def list_product_handles() -> list[str]:
    html = fetch(COLLECTION_URL)
    handles = sorted({m.group(0).split('/')[-1] for m in PRODUCT_LINK_RE.finditer(html)})
    priority = ['pla-basic-filament', 'pla-matte', 'petg-basic', 'petg-hf', 'abs-filament']
    return priority + [h for h in handles if h not in priority]


def parse_collection_listings(html: str) -> dict[str, dict[str, Any]]:
    text = decode_chunks(html)
    listings: dict[str, dict[str, Any]] = {}
    for match in LISTING_RE.finditer(text):
        handle = match.group('handle')
        listings[handle] = {
            'product': match.group('name'),
            'price': float(match.group('price')),
            'sale_price': float(match.group('lower')),
        }
    return listings


def parse_sku_availability(text: str) -> dict[str, bool]:
    """Map Bambu store SKU id -> in_stock (from isSoldOut in RSC payload)."""
    import json

    stock: dict[str, bool] = {}
    for line in text.split('\n'):
        if '"isSoldOut"' not in line or '"price"' not in line:
            continue
        try:
            _, _, payload = line.partition(':')
            obj = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        sku_id = obj.get('id')
        if sku_id is None or 'isSoldOut' not in obj:
            continue
        stock[str(sku_id)] = not bool(obj['isSoldOut'])
    return stock


def parse_product_page(html: str, handle: str) -> list[dict[str, Any]]:
    text = decode_chunks(html)
    group = PRODUCT_GROUP_NAME_RE.search(text)
    default_line = group.group('name').strip() if group else handle.replace('-', ' ').title()

    names = list(VARIANT_NAME_RE.finditer(text))
    skus = [m.group('sku') for m in VARIANT_SKU_RE.finditer(text)]
    sku_prices = {
        m.group('sku'): {
            'price': float(m.group('price')),
            'sale_price': None if m.group('disc') == 'null' else float(m.group('disc')),
        }
        for m in SKU_PRICE_RE.finditer(text)
    }
    if not names or not skus:
        return []

    count = len(names)
    variant_skus = skus[:count]
    if len(variant_skus) < count:
        return []

    image_urls = re.findall(
        r'"image":\s*"(https://store\.bblcdn\.eu/[^"]+)"',
        text,
    )
    bulk_by_sku = parse_bulk_discounts(text)
    stock_by_sku = parse_sku_availability(text)

    rows: list[dict[str, Any]] = []
    for idx, match in enumerate(names):
        line = match.group('line').strip() or default_line
        color = match.group('color').strip()
        spool = match.group('spool').strip()
        weight = match.group('weight').strip()
        weight_g = parse_weight_g(weight)
        store_sku = variant_skus[idx]
        price_info = sku_prices.get(store_sku, {})
        price = price_info.get('price')
        sale_price = price_info.get('sale_price')
        effective = sale_price if sale_price is not None else price
        bulk_tiers = bulk_by_sku.get(store_sku, [])
        bulk_tier = bulk_tier_at_moq(bulk_tiers, BULK_MOQ) if bulk_tiers and weight_g == 1000 else None
        bulk_unit_price = bulk_tier['unit_price'] if bulk_tier else None
        bulk_moq = BULK_MOQ if bulk_unit_price is not None else None
        image_url = image_urls[idx] if idx < len(image_urls) else ''
        rows.append(
            {
                'brand': 'Bambu Lab',
                'source': 'bambulab.com',
                'product': line,
                'variant': f'{color} / {spool} / {weight}',
                'material': infer_material(line),
                'weight_g': weight_g,
                'price': price,
                'sale_price': sale_price,
                'currency': 'EUR',
                'price_per_kg': round(effective * 1000 / weight_g, 2) if effective and weight_g else None,
                'bulk_tiers': bulk_tiers,
                'bulk_moq': bulk_moq,
                'bulk_unit_price': bulk_unit_price,
                'bulk_price_per_kg': round(bulk_unit_price * 1000 / weight_g, 2) if bulk_unit_price and weight_g else None,
                'url': f'{STORE_BASE}/en/products/{handle}?id={store_sku}',
                'image_url': image_url,
                'sku': store_sku,
                'in_stock': stock_by_sku.get(store_sku, True),
            }
        )
    return rows


def scrape_bambu(
    verbose: bool = True,
    delay_s: float = 1.2,
    max_products: int | None = None,
) -> list[dict[str, Any]]:
    handles = list_product_handles()
    if max_products is not None:
        handles = handles[:max_products]

    collection_html = fetch(COLLECTION_URL)
    listings = parse_collection_listings(collection_html)
    all_rows: list[dict[str, Any]] = []
    fallback_rows: list[dict[str, Any]] = []

    if verbose:
        print(f'[bambu] {len(handles)} products on EU store')

    for index, handle in enumerate(handles):
        url = f'{STORE_BASE}/en/products/{handle}'
        try:
            html = fetch(url)
            rows = parse_product_page(html, handle)
        except Exception as exc:
            if verbose:
                print(f'  x {handle}: {exc}')
            rows = []
        if rows:
            all_rows.extend(rows)
            if verbose:
                print(f'  + {handle}: {len(rows)} variants')
        elif handle in listings:
            listing = listings[handle]
            price = listing['sale_price']
            fallback_rows.append(
                {
                    'brand': 'Bambu Lab',
                    'source': 'bambulab.com',
                    'product': listing['product'],
                    'variant': 'from price',
                    'material': infer_material(listing['product']),
                    'weight_g': 1000,
                    'price': listing['price'],
                    'sale_price': price if price != listing['price'] else None,
                    'currency': 'EUR',
                    'price_per_kg': price,
                    'url': f'{STORE_BASE}/en/products/{handle}',
                    'image_url': '',
                    'sku': '',
                    'in_stock': True,
                }
            )
            if verbose:
                print(f'  ~ {handle}: listing fallback')
        if index < len(handles) - 1:
            time.sleep(delay_s)

    if not all_rows and fallback_rows:
        all_rows = fallback_rows
    return all_rows
