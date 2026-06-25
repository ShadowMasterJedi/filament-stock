"""Match inventory items to FilamentScraper price rows (Bambu SKU + SUNLU fuzzy)."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

_COLOR_ALIASES: dict[str, str] = {
    'hvid': 'white', 'weiß': 'white', 'weiss': 'white', 'white': 'white', 'wt': 'white',
    'sort': 'black', 'schwarz': 'black', 'black': 'black', 'bk': 'black',
    'rød': 'red', 'rod': 'red', 'rot': 'red', 'red': 'red',
    'blå': 'blue', 'bla': 'blue', 'blau': 'blue', 'blue': 'blue',
    'grøn': 'green', 'gron': 'green', 'grün': 'green', 'grun': 'green', 'green': 'green',
    'gul': 'yellow', 'gelb': 'yellow', 'yellow': 'yellow',
    'orange': 'orange',
    'lilla': 'purple', 'purple': 'purple', 'violett': 'purple', 'violet': 'purple',
    'grå': 'gray', 'gra': 'gray', 'grau': 'gray', 'gray': 'gray', 'grey': 'gray',
    'sølv': 'silver', 'soelv': 'silver', 'silber': 'silver', 'silver': 'silver',
    'guld': 'gold', 'gold': 'gold',
    'jade': 'jade', 'ivory': 'ivory', 'elfenbein': 'ivory',
    'transparent': 'clear', 'clear': 'clear', 'klar': 'clear',
    'natur': 'natural', 'natural': 'natural',
    'silke': 'silk', 'silk': 'silk',
}


def normalize_brand(brand: str) -> str:
    upper = (brand or '').strip().lower()
    if 'bambu' in upper:
        return 'Bambu Lab'
    if 'sunlu' in upper:
        return 'SUNLU'
    return (brand or '').strip()


def normalize_material(material: str) -> str:
    mat = (material or 'Andet').strip().upper()
    if mat in ('PLA+', 'PLA PLUS', 'PLA PLUS+'):
        return 'PLA+'
    if mat.startswith('PLA'):
        return 'PLA'
    return mat


def materials_compatible(item_mat: str, row_mat: str) -> bool:
    a = normalize_material(item_mat)
    b = normalize_material(row_mat)
    if a == b:
        return True
    if {a, b} <= {'PLA', 'PLA+'}:
        return True
    return False


def _ascii_lower(text: str) -> str:
    folded = unicodedata.normalize('NFKD', text.lower())
    return ''.join(ch for ch in folded if not unicodedata.combining(ch))


def color_tokens(*parts: str) -> set[str]:
    tokens: set[str] = set()
    for part in parts:
        if not part:
            continue
        clean = _ascii_lower(part)
        clean = re.sub(r'[^a-z0-9+#]+', ' ', clean)
        for word in clean.split():
            if len(word) < 2 and word not in ('wt', 'bk'):
                continue
            canon = _COLOR_ALIASES.get(word, word)
            tokens.add(canon)
            if len(word) >= 4:
                tokens.add(word)
    return tokens


def searchable_text(row: dict[str, Any]) -> str:
    return _ascii_lower(' '.join([
        str(row.get('product') or ''),
        str(row.get('variant') or ''),
        str(row.get('material') or ''),
    ]))


def build_sku_index(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for row in items:
        sku = str(row.get('sku') or '').strip()
        if sku:
            index[sku] = row
    return index


def score_price_row(item: dict[str, Any], row: dict[str, Any]) -> int:
    item_brand = normalize_brand(item.get('brand', ''))
    row_brand = normalize_brand(row.get('brand', ''))
    if item_brand and row_brand and item_brand != row_brand:
        return -1

    if not materials_compatible(item.get('material', ''), row.get('material', '')):
        return -1

    score = 0
    item_weight = int(item.get('weight_g') or 1000)
    row_weight = int(row.get('weight_g') or 1000) or 1000
    if item_weight == row_weight:
        score += 12
    elif abs(item_weight - row_weight) <= 250:
        score += 6

    item_tokens = color_tokens(
        item.get('color', ''),
        item.get('notes', ''),
        item.get('bambu_code', ''),
    )
    hay = searchable_text(row)
    if item_tokens:
        hits = sum(1 for token in item_tokens if token in hay)
        if hits == 0:
            return -1
        score += hits * 18
    elif item_brand == 'SUNLU':
        score += 4

    if row.get('in_stock') is True:
        score += 8
    elif row.get('in_stock') is False:
        score -= 6

    if row.get('weight_g') == 1000:
        score += 5

    return score


def resolve_price_row(
    item: dict[str, Any],
    sku_index: dict[str, dict[str, Any]],
    price_items: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, str | None]:
    """Return (price_row, match_via)."""
    store_sku = (item.get('store_sku') or '').strip()
    if store_sku and store_sku in sku_index:
        return sku_index[store_sku], 'store_sku'

    brand = normalize_brand(item.get('brand', ''))
    if brand == 'Bambu Lab':
        code = (item.get('bambu_code') or '').strip()
        if not code and str(item.get('barcode', '')).strip().isdigit():
            code = str(item['barcode']).strip()
        if code:
            import db

            bambu = db.lookup_bambu(code)
            if bambu:
                sku = str(bambu.get('store_sku') or '').strip()
                if sku and sku in sku_index:
                    return sku_index[sku], 'bambu_code'

    best_score = 0
    best_row: dict[str, Any] | None = None
    for row in price_items:
        if row.get('currency') != 'EUR':
            continue
        score = score_price_row(item, row)
        if score > best_score:
            best_score = score
            best_row = row

    if best_row and best_score >= 18:
        via = 'sunlu_fuzzy' if brand == 'SUNLU' else 'fuzzy'
        return best_row, via
    return None, None
