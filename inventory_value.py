"""Match inventory to FilamentScraper prices and compute tied-up capital."""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import db
from price_match import build_sku_index, normalize_brand, resolve_price_row

ROOT = Path(__file__).resolve().parent
PRICES_CACHE_PATH = ROOT / 'filamentscraper' / 'data' / 'prices_cache.json'
SCRAPER_PRICES_URL = 'http://127.0.0.1:8095/api/prices'
SCRAPER_PORT = 8095
LOW_STOCK_THRESHOLD = 1
PRICE_DROP_PCT = 3.0
MIN_DISCOUNT_ALERT_PCT = 5.0


def load_price_cache() -> dict[str, Any] | None:
    """Load scraped prices from cache file, with HTTP fallback to FilamentScraper."""
    if PRICES_CACHE_PATH.exists():
        try:
            return json.loads(PRICES_CACHE_PATH.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, OSError):
            pass

    try:
        req = urllib.request.Request(
            SCRAPER_PRICES_URL,
            headers={'User-Agent': 'FilamentStock/1.0'},
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except (urllib.error.URLError, json.JSONDecodeError, OSError, TimeoutError):
        return None


def spool_replacement_eur(price_row: dict[str, Any], weight_g: int) -> float | None:
    """Current replacement cost for one spool (list/sale price, not volume MOQ)."""
    sale = price_row.get('sale_price')
    price = price_row.get('price')
    if sale is not None:
        unit = float(sale)
    elif price is not None:
        unit = float(price)
    else:
        return None

    row_weight = int(price_row.get('weight_g') or 1000)
    target_weight = int(weight_g or 1000)
    if target_weight != row_weight and target_weight > 0:
        ppk = price_row.get('price_per_kg')
        if ppk is not None:
            return round(float(ppk) * target_weight / 1000, 2)
        if row_weight > 0:
            return round(unit * target_weight / row_weight, 2)
    return round(unit, 2)


def effective_ppk(price_row: dict[str, Any]) -> float | None:
    for key in ('max_discount_price_per_kg', 'price_per_kg'):
        val = price_row.get(key)
        if val is not None:
            return float(val)
    unit = spool_replacement_eur(price_row, int(price_row.get('weight_g') or 1000))
    weight = int(price_row.get('weight_g') or 1000)
    if unit is not None and weight > 0:
        return round(unit * 1000 / weight, 2)
    return None


def lan_ip() -> str | None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(('8.8.8.8', 80))
            return sock.getsockname()[0]
    except OSError:
        return None


def scraper_base_url() -> str:
    host = lan_ip() or 'localhost'
    return f'http://{host}:{SCRAPER_PORT}'


def scraper_link(
    *,
    view: str = 'list',
    material: str = '',
    brand: str = '',
    q: str = '',
) -> str:
    params: dict[str, str] = {}
    if view and view != 'overview':
        params['view'] = view
    if material:
        params['material'] = material
    if brand:
        params['brand'] = brand
    if q:
        params['q'] = q
    base = scraper_base_url()
    if not params:
        return f'{base}/'
    return f'{base}/?{urllib.parse.urlencode(params)}'


def normalize_scraper_brand(brand: str) -> str:
    mapped = normalize_brand(brand)
    return mapped if mapped in ('Bambu Lab', 'SUNLU') else ''


def best_material_deal(price_items: list[dict[str, Any]], material: str) -> dict[str, Any] | None:
    candidates: list[tuple[float, dict[str, Any]]] = []
    for row in price_items:
        if row.get('material') != material:
            continue
        if row.get('weight_g') != 1000:
            continue
        if row.get('currency') != 'EUR':
            continue
        if row.get('in_stock') is False:
            continue
        ppk = row.get('max_discount_price_per_kg') or row.get('price_per_kg')
        if ppk is None:
            continue
        candidates.append((float(ppk), row))
    if not candidates:
        return None
    candidates.sort(key=lambda pair: pair[0])
    ppk, row = candidates[0]
    return {
        'price_per_kg': round(ppk, 2),
        'brand': row.get('brand', ''),
        'product': row.get('product', ''),
        'url': row.get('url', ''),
        'has_volume_discount': bool(row.get('max_discount_price_per_kg')),
    }


def rabat_link_for_item(item: dict[str, Any], price_row: dict[str, Any] | None) -> str:
    material = item.get('material') or ''
    brand = normalize_scraper_brand(item.get('brand', ''))
    q = (item.get('color') or '').strip() or (item.get('bambu_code') or '').strip()
    if price_row and price_row.get('product'):
        q = str(price_row.get('variant') or price_row.get('product') or q)
    return scraper_link(view='maxrabat', material=material, brand=brand, q=q)


def item_price_context(
    item: dict[str, Any],
    sku_index: dict[str, dict[str, Any]],
    price_items: list[dict[str, Any]],
) -> dict[str, Any]:
    price_row, match_via = resolve_price_row(item, sku_index, price_items)
    unit_eur = spool_replacement_eur(price_row, int(item.get('weight_g') or 1000)) if price_row else None
    ppk = effective_ppk(price_row) if price_row else None
    discount_pct = float(price_row.get('discount_pct') or 0) if price_row else 0.0
    max_ppk = price_row.get('max_discount_price_per_kg') if price_row else None
    has_rabat = max_ppk is not None and ppk is not None and float(max_ppk) < float(ppk or max_ppk)
    return {
        'price_row': price_row,
        'match_via': match_via,
        'unit_eur': unit_eur,
        'ppk': ppk,
        'discount_pct': discount_pct,
        'has_rabat': has_rabat,
        'max_discount_ppk': float(max_ppk) if max_ppk is not None else None,
    }


def compute_low_stock(threshold: int = LOW_STOCK_THRESHOLD) -> dict[str, Any]:
    filaments = db.list_filaments()
    cache = load_price_cache()
    price_items = (cache or {}).get('items') or []
    sku_index = build_sku_index(price_items)

    rows: list[dict[str, Any]] = []
    for item in filaments:
        qty = int(item.get('quantity') or 0)
        if qty > threshold:
            continue

        material = item.get('material') or 'Andet'
        brand = item.get('brand', '')
        color = item.get('color', '')
        scraper_brand = normalize_scraper_brand(brand)
        search_q = color.strip() or (item.get('bambu_code') or '').strip()

        ctx = item_price_context(item, sku_index, price_items)
        price_row = ctx['price_row']
        material_deal = best_material_deal(price_items, material)

        rabat_hint = None
        if ctx['has_rabat'] and ctx['max_discount_ppk'] is not None:
            rabat_hint = f"Rabatkøb fra €{ctx['max_discount_ppk']:.2f}/kg"
        elif material_deal and material_deal.get('has_volume_discount'):
            rabat_hint = f"Bedste {material}-rabat €{material_deal['price_per_kg']:.2f}/kg"

        rows.append({
            'id': item['id'],
            'barcode': item['barcode'],
            'brand': brand,
            'material': material,
            'color': color,
            'bambu_code': item.get('bambu_code', ''),
            'quantity': qty,
            'status': 'tom' if qty <= 0 else 'lav',
            'matched': price_row is not None,
            'match_via': ctx['match_via'],
            'product_url': price_row.get('url') if price_row else None,
            'unit_eur': ctx['unit_eur'],
            'scraper_url': scraper_link(
                view='list',
                material=material,
                brand=scraper_brand,
                q=search_q,
            ),
            'scraper_rabat_url': rabat_link_for_item(item, price_row),
            'deal_hint': rabat_hint or (
                f"Bedste {material} fra €{material_deal['price_per_kg']:.2f}/kg ({material_deal['brand']})"
                if material_deal else None
            ),
            'deal_url': material_deal.get('url') if material_deal else None,
        })

    rows.sort(key=lambda row: (row['quantity'], row['material'], row['color']))
    return {
        'ok': True,
        'threshold': threshold,
        'count': len(rows),
        'prices_available': bool(price_items),
        'scraper_base': scraper_base_url(),
        'items': rows,
    }


def compute_price_alerts() -> dict[str, Any]:
    filaments = [f for f in db.list_filaments() if int(f.get('quantity') or 0) > 0]
    cache = load_price_cache()
    price_items = (cache or {}).get('items') or []
    sku_index = build_sku_index(price_items)

    alerts: list[dict[str, Any]] = []
    for item in filaments:
        ctx = item_price_context(item, sku_index, price_items)
        price_row = ctx['price_row']
        if not price_row:
            continue

        unit = ctx['unit_eur']
        ppk = ctx['ppk']
        watch = db.get_price_watch(item['id'])
        reasons: list[str] = []

        if ctx['discount_pct'] >= MIN_DISCOUNT_ALERT_PCT:
            reasons.append(f"{ctx['discount_pct']:.0f}% rabat lige nu")

        if ctx['has_rabat'] and ctx['max_discount_ppk'] is not None:
            reasons.append(f"Rabatkøb €{ctx['max_discount_ppk']:.2f}/kg")

        if watch and watch.get('last_unit_eur') and unit is not None:
            prev = float(watch['last_unit_eur'])
            if prev > 0 and unit < prev * (1 - PRICE_DROP_PCT / 100):
                drop = round((1 - unit / prev) * 100)
                reasons.append(f"Prisfald {drop}% (var €{prev:.2f})")

        if watch and watch.get('last_ppk') and ppk is not None:
            prev_ppk = float(watch['last_ppk'])
            if prev_ppk > 0 and ppk < prev_ppk * (1 - PRICE_DROP_PCT / 100):
                drop = round((1 - ppk / prev_ppk) * 100)
                reasons.append(f"€/kg faldet {drop}%")

        db.upsert_price_watch(item['id'], unit, ppk)

        if not reasons:
            continue

        material = item.get('material') or 'Andet'
        scraper_brand = normalize_scraper_brand(item.get('brand', ''))
        search_q = (item.get('color') or '').strip() or (item.get('bambu_code') or '').strip()

        alerts.append({
            'id': item['id'],
            'barcode': item['barcode'],
            'brand': item.get('brand', ''),
            'material': material,
            'color': item.get('color', ''),
            'quantity': int(item.get('quantity') or 0),
            'match_via': ctx['match_via'],
            'unit_eur': unit,
            'ppk': ppk,
            'discount_pct': ctx['discount_pct'],
            'reasons': reasons,
            'product_url': price_row.get('url'),
            'scraper_url': scraper_link(view='list', material=material, brand=scraper_brand, q=search_q),
            'scraper_rabat_url': rabat_link_for_item(item, price_row),
        })

    alerts.sort(key=lambda row: (len(row['reasons']), row.get('discount_pct', 0)), reverse=True)
    return {
        'ok': True,
        'prices_available': bool(price_items),
        'prices_updated_at': (cache or {}).get('updated_at'),
        'count': len(alerts),
        'items': alerts,
    }


def compute_inventory_value() -> dict[str, Any]:
    filaments = [f for f in db.list_filaments() if int(f.get('quantity') or 0) > 0]
    cache = load_price_cache()
    price_items = (cache or {}).get('items') or []
    sku_index = build_sku_index(price_items)

    total_eur = 0.0
    matched_spools = 0
    unmatched_spools = 0
    by_material: dict[str, dict[str, Any]] = {}
    rows: list[dict[str, Any]] = []

    for item in filaments:
        qty = int(item.get('quantity') or 0)
        material = item.get('material') or 'Andet'
        mat_bucket = by_material.setdefault(
            material,
            {'material': material, 'value_eur': 0.0, 'spools': 0, 'matched_spools': 0},
        )
        mat_bucket['spools'] += qty

        ctx = item_price_context(item, sku_index, price_items)
        price_row = ctx['price_row']
        unit_eur = ctx['unit_eur']

        entry = {
            'id': item['id'],
            'barcode': item['barcode'],
            'brand': item.get('brand', ''),
            'material': material,
            'color': item.get('color', ''),
            'quantity': qty,
            'weight_g': item.get('weight_g', 1000),
            'matched': unit_eur is not None,
            'match_via': ctx['match_via'],
            'store_sku': (item.get('store_sku') or (price_row or {}).get('sku') or ''),
            'unit_eur': unit_eur,
            'value_eur': round(unit_eur * qty, 2) if unit_eur is not None else None,
            'in_stock': price_row.get('in_stock') if price_row else None,
            'price_url': price_row.get('url') if price_row else None,
        }
        rows.append(entry)

        if unit_eur is not None:
            matched_spools += qty
            total_eur += entry['value_eur']
            mat_bucket['value_eur'] = round(mat_bucket['value_eur'] + entry['value_eur'], 2)
            mat_bucket['matched_spools'] += qty
            db.upsert_price_watch(item['id'], unit_eur, ctx['ppk'])
        else:
            unmatched_spools += qty

    total_spools = matched_spools + unmatched_spools
    by_material_list = sorted(
        [
            {
                **bucket,
                'value_eur': round(bucket['value_eur'], 2),
            }
            for bucket in by_material.values()
        ],
        key=lambda row: row['value_eur'],
        reverse=True,
    )

    return {
        'ok': True,
        'prices_available': bool(price_items),
        'prices_updated_at': (cache or {}).get('updated_at'),
        'price_source': 'cache' if PRICES_CACHE_PATH.exists() else ('api' if price_items else None),
        'total_eur': round(total_eur, 2),
        'matched_spools': matched_spools,
        'unmatched_spools': unmatched_spools,
        'total_spools': total_spools,
        'matched_skus': sum(1 for row in rows if row['matched']),
        'unmatched_skus': sum(1 for row in rows if not row['matched']),
        'sku_count': len(rows),
        'by_material': by_material_list,
        'items': rows,
    }
