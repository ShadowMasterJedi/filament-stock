"""Scrape SUNLU filament prices from de.store.sunlu.com (EU / EUR)."""

from __future__ import annotations

import re
import time
from typing import Any

from .http_util import fetch_json

STORE_BASE = 'https://de.store.sunlu.com'
SITE_BASE = 'https://de.store.sunlu.com'
COLLECTION_HANDLE = '3d-drucker-filament'


def infer_material(title: str, product_type: str = '') -> str:
    text = f'{title} {product_type}'.upper()
    rules = [
        ('PLA+', 'PLA+'),
        ('PLA ', 'PLA'),
        ('PLA', 'PLA'),
        ('PETG', 'PETG'),
        ('ABS', 'ABS'),
        ('ASA', 'ASA'),
        ('TPU', 'TPU'),
        ('NYLON', 'NYLON'),
        ('PA ', 'NYLON'),
        ('PC ', 'PC'),
        ('PVA', 'PVA'),
        ('HIPS', 'HIPS'),
        ('SILK', 'PLA'),
        ('WOOD', 'PLA'),
        ('CARBON', 'CF'),
        ('KOHLENFASER', 'CF'),
    ]
    for needle, material in rules:
        if needle in text:
            return material
    return 'Other'


def parse_weight_g(title: str, variant_title: str = '') -> int | None:
    text = f'{title} {variant_title}'
    m = re.search(r'(\d+(?:\.\d+)?)\s*kg', text, re.I)
    if m:
        return int(float(m.group(1)) * 1000)
    m = re.search(r'(\d+)\s*g\b', text, re.I)
    if m:
        return int(m.group(1))
    return None


def is_filament_product(title: str, product_type: str, tags: list[str]) -> bool:
    hay = f'{title} {product_type} {" ".join(tags)}'.lower()
    if any(skip in hay for skip in ('harz', 'resin', 'trockner', 'dryer', 'connector', 'printer', 'scanner', 'pen', 'heizgerät', 'heater')):
        if 'filament' not in hay and 'filamente' not in hay:
            return False
    return any(token in hay for token in ('filament', 'filamente', 'pla', 'petg', 'abs', 'asa', 'tpu', 'nylon'))


def fetch_collection_products(
    collection: str = COLLECTION_HANDLE,
    page_size: int = 250,
    delay_s: float = 0.4,
) -> list[dict[str, Any]]:
    products: dict[int, dict[str, Any]] = {}
    page = 1
    while True:
        url = f'{STORE_BASE}/collections/{collection}/products.json?limit={page_size}&page={page}'
        data = fetch_json(url)
        batch = data.get('products', []) if isinstance(data, dict) else []
        if not batch:
            break
        for product in batch:
            products[product['id']] = product
        if len(batch) < page_size:
            break
        page += 1
        time.sleep(delay_s)
    return list(products.values())


def normalize_product(product: dict[str, Any]) -> list[dict[str, Any]]:
    title = product.get('title', '').strip()
    product_type = product.get('product_type', '') or ''
    tags = product.get('tags', []) or []
    if not is_filament_product(title, product_type, tags):
        return []

    handle = product.get('handle', '')
    image_url = ''
    if product.get('images'):
        image_url = product['images'][0].get('src', '')
    material = infer_material(title, product_type)
    store_url = f'{STORE_BASE}/products/{handle}'

    rows: list[dict[str, Any]] = []
    for variant in product.get('variants', []):
        variant_title = (variant.get('title') or 'Default').strip()
        if variant_title.lower() == 'default title':
            variant_title = title
        price_raw = variant.get('price')
        if price_raw in (None, ''):
            continue
        current = float(price_raw)
        compare_raw = variant.get('compare_at_price')
        compare_price = float(compare_raw) if compare_raw not in (None, '') else None
        on_sale = compare_price is not None and compare_price > current
        price = compare_price if on_sale else current
        sale_price = current if on_sale else None
        weight_g = parse_weight_g(title, variant_title) or int(variant.get('grams') or 0) or None
        effective = current
        rows.append(
            {
                'brand': 'SUNLU',
                'source': 'de.store.sunlu.com',
                'product': title,
                'variant': variant_title,
                'material': material,
                'weight_g': weight_g,
                'price': price,
                'sale_price': sale_price,
                'currency': 'EUR',
                'price_per_kg': round(effective * 1000 / weight_g, 2) if weight_g else None,
                'url': store_url,
                'store_url': store_url,
                'image_url': image_url,
                'sku': variant.get('sku') or str(variant.get('id', '')),
                'in_stock': bool(variant.get('available', False)),
            }
        )
    return rows


def scrape_sunlu(verbose: bool = True) -> list[dict[str, Any]]:
    products = fetch_collection_products()
    if verbose:
        print(f'[sunlu] {len(products)} products from DE store')
    rows: list[dict[str, Any]] = []
    for product in products:
        product_rows = normalize_product(product)
        rows.extend(product_rows)
        if verbose and product_rows:
            print(f'  + {product.get("title", "")[:60]}: {len(product_rows)} variants')
    return rows
