"""Find good filament buys from scraped price rows."""

from __future__ import annotations

import re
from typing import Any

COMPARE_MATERIALS = ('PLA', 'PLA+', 'PETG', 'ABS', 'ASA', 'TPU')
SALE_MIN_PCT = 15.0
DROP_MIN_PCT = 5.0
BEAT_BRAND_PCT = 5.0
MAX_DISCOUNT_MIN_PCT = 10.0

MOQ_RE = re.compile(r'\[?\s*MOQ[:\s]*(\d+)\s*Roll', re.I)


def effective_price(row: dict[str, Any]) -> float | None:
    if row.get('sale_price') is not None:
        return float(row['sale_price'])
    if row.get('price') is not None:
        return float(row['price'])
    return None


def best_volume_deal(row: dict[str, Any]) -> dict[str, Any] | None:
    """Lowest unit price including quantity tiers (SUNLU MOQ, Bambu 10-pack)."""
    list_unit = float(row['price']) if row.get('price') is not None else None
    if list_unit is None:
        return None

    options: list[dict[str, Any]] = []
    sale_unit = row.get('sale_price')
    single_unit = float(sale_unit) if sale_unit is not None else list_unit
    options.append({'moq': 1, 'unit': single_unit, 'source': 'single'})

    title_moq = parse_moq(row.get('product', ''))
    if title_moq > 1 and sale_unit is not None:
        options.append({'moq': title_moq, 'unit': float(sale_unit), 'source': 'sunlu_moq'})

    bulk_unit = row.get('bulk_unit_price')
    bulk_moq = row.get('bulk_moq')
    if bulk_unit is not None and bulk_moq:
        options.append({'moq': int(bulk_moq), 'unit': float(bulk_unit), 'source': 'bulk'})

    best = min(options, key=lambda opt: opt['unit'])
    best['list_unit'] = list_unit
    best['total'] = round(best['unit'] * best['moq'], 2)
    best['was_total'] = round(list_unit * best['moq'], 2)
    best['save'] = round(best['was_total'] - best['total'], 2)
    best['discount_pct'] = round((list_unit - best['unit']) / list_unit * 100, 1) if list_unit else 0.0
    return best


def discount_pct(row: dict[str, Any]) -> float:
    deal = best_volume_deal(row)
    if deal and deal['discount_pct'] > 0:
        return float(deal['discount_pct'])
    price = row.get('price')
    sale = row.get('sale_price')
    if price is None or sale is None or sale >= price:
        return 0.0
    return (float(price) - float(sale)) / float(price) * 100.0


def row_key(row: dict[str, Any]) -> str:
    return f"{row.get('brand', '')}|{row.get('sku', '')}|{row.get('variant', '')}"


def is_standard_1kg(row: dict[str, Any]) -> bool:
    return row.get('weight_g') == 1000


def compare_price_per_kg(row: dict[str, Any]) -> float | None:
    return row.get('max_discount_price_per_kg') or row.get('price_per_kg')


def parse_moq(product_title: str) -> int:
    match = MOQ_RE.search(product_title or '')
    if match:
        return max(1, int(match.group(1)))
    return 1


def product_family(title: str) -> str:
    family = MOQ_RE.sub('', title or '')
    family = family.strip()
    return family or title


def enrich_item(row: dict[str, Any]) -> dict[str, Any]:
    deal = best_volume_deal(row)
    if deal:
        row['moq'] = deal['moq']
        row['discount_pct'] = deal['discount_pct']
        row['bundle_total'] = deal['total']
        row['bundle_was_total'] = deal['was_total']
        row['bundle_save'] = deal['save']
        row['max_discount_unit'] = deal['unit']
        row['max_discount_source'] = deal['source']
        weight_g = row.get('weight_g') or 0
        if weight_g:
            row['max_discount_price_per_kg'] = round(deal['unit'] * 1000 / weight_g, 2)
        return row

    moq = parse_moq(row.get('product', ''))
    unit = effective_price(row)
    list_unit = float(row['price']) if row.get('price') is not None else unit
    pct = 0.0
    row['moq'] = moq
    row['discount_pct'] = pct
    if unit is not None:
        row['bundle_total'] = round(unit * moq, 2)
        row['bundle_was_total'] = round(list_unit * moq, 2) if list_unit else None
        row['bundle_save'] = 0.0
    else:
        row['bundle_total'] = None
        row['bundle_was_total'] = None
        row['bundle_save'] = 0.0
    return row


def is_in_stock(row: dict[str, Any]) -> bool:
    return bool(row.get('in_stock', True))


def compute_max_discount_buys(
    items: list[dict[str, Any]],
    *,
    limit: int = 12,
) -> list[dict[str, Any]]:
    """Best 1 kg buys when purchasing at minimum quantity for full discount."""
    picks: list[dict[str, Any]] = []
    seen_families: set[str] = set()

    candidates = [
        row for row in items
        if is_standard_1kg(row)
        and is_in_stock(row)
        and row.get('currency') == 'EUR'
        and row.get('discount_pct', discount_pct(row)) >= MAX_DISCOUNT_MIN_PCT
    ]
    candidates.sort(
        key=lambda r: (
            r.get('max_discount_price_per_kg', r.get('price_per_kg', 999)),
            -r.get('discount_pct', 0),
        )
    )

    for row in candidates:
        material = row.get('material') or 'Other'
        family = f"{row.get('brand', '')}|{material}|{product_family(row.get('product', ''))}"
        if family in seen_families:
            continue
        seen_families.add(family)

        moq = row.get('moq', 1)
        unit = row.get('max_discount_unit') or effective_price(row)
        bundle = row.get('bundle_total')
        was = row.get('bundle_was_total')
        save = row.get('bundle_save', 0)
        pct = row.get('discount_pct', 0)
        ppk = row.get('max_discount_price_per_kg') or row.get('price_per_kg')

        if moq > 1:
            bulk_note = ' (10 stk rabat)' if row.get('max_discount_source') == 'bulk' else ''
            reason = (
                f'Køb min. {moq} stk à {unit:.2f} € = {bundle:.2f} € total{bulk_note} '
                f'(spar {pct:.0f}% / {save:.2f} € vs enkeltpris)'
            )
        else:
            reason = f'{pct:.0f}% rabat — {unit:.2f} €/kg (ingen minimumsmængde)'

        picks.append(
            {
                'type': 'max_discount',
                'score': pct + (10 if moq > 1 else 0),
                'title': row.get('product', ''),
                'reason': reason,
                'item': row,
                'material': material,
                'moq': moq,
                'discount_pct': pct,
                'bundle_total': bundle,
                'bundle_save': save,
                'price_per_kg': ppk,
            }
        )
        if len(picks) >= limit:
            break

    # Ensure at least one pick per major material where possible.
    by_material: dict[str, dict[str, Any]] = {}
    for pick in picks:
        mat = pick.get('material', 'Other')
        if mat in COMPARE_MATERIALS and mat not in by_material:
            by_material[mat] = pick

    for row in sorted(candidates, key=lambda r: r.get('max_discount_price_per_kg', r.get('price_per_kg', 999))):
        mat = row.get('material') or 'Other'
        if mat not in COMPARE_MATERIALS or mat in by_material:
            continue
        moq = row.get('moq', 1)
        unit = effective_price(row)
        pct = row.get('discount_pct', 0)
        bundle = row.get('bundle_total')
        save = row.get('bundle_save', 0)
        by_material[mat] = {
            'type': 'max_discount',
            'score': pct,
            'title': row.get('product', ''),
            'reason': (
                f'Køb min. {moq} stk à {unit:.2f} € = {bundle:.2f} €'
                if moq > 1
                else f'{pct:.0f}% rabat — {unit:.2f} €/kg'
            ),
            'item': row,
            'material': mat,
            'moq': moq,
            'discount_pct': pct,
            'bundle_total': bundle,
            'bundle_save': save,
        }

    merged = list(by_material.values())
    for pick in picks:
        if pick not in merged:
            merged.append(pick)
    merged.sort(key=lambda p: (-p.get('discount_pct', 0), p['item'].get('price_per_kg', 999)))
    return merged[:limit]


def compute_deals(
    items: list[dict[str, Any]],
    history: dict[str, Any] | None = None,
    *,
    limit: int = 24,
) -> list[dict[str, Any]]:
    deals: list[dict[str, Any]] = []
    seen_keys: set[str] = set()

    def add_deal(deal: dict[str, Any]) -> None:
        key = row_key(deal['item'])
        if key in seen_keys:
            return
        seen_keys.add(key)
        deals.append(deal)

    # On-sale items with meaningful discount (1 kg preferred).
    for row in items:
        pct = discount_pct(row)
        if pct < SALE_MIN_PCT:
            continue
        if not is_standard_1kg(row):
            continue
        add_deal(
            {
                'type': 'sale',
                'score': pct + 10,
                'title': row['product'],
                'reason': f'{pct:.0f}% rabat – nu {row["currency"]} {effective_price(row):.2f}/kg' if row.get('price_per_kg') else f'{pct:.0f}% rabat',
                'item': row,
                'discount_pct': round(pct, 1),
            }
        )

    # Cheapest per kg per material (1 kg, both brands in EUR).
    by_material: dict[str, list[dict[str, Any]]] = {}
    for row in items:
        if not is_standard_1kg(row):
            continue
        if row.get('currency') != 'EUR':
            continue
        material = row.get('material') or 'Other'
        if material not in COMPARE_MATERIALS:
            continue
        ppk = compare_price_per_kg(row)
        if ppk is None:
            continue
        by_material.setdefault(material, []).append(row)

    for material, rows in by_material.items():
        rows.sort(key=lambda r: compare_price_per_kg(r) or 999)
        if not rows:
            continue
        best = rows[0]
        best_ppk = compare_price_per_kg(best)
        add_deal(
            {
                'type': 'cheapest',
                'score': 80 - best_ppk,
                'title': best['product'],
                'reason': f'Billigste {material} 1 kg: €{best_ppk:.2f}/kg ({best["brand"]})',
                'item': best,
                'material': material,
            }
        )

    # Cross-brand: SUNLU beats Bambu on €/kg for same material.
    for material in COMPARE_MATERIALS:
        rows = by_material.get(material, [])
        bambu = [r for r in rows if r['brand'] == 'Bambu Lab']
        sunlu = [r for r in rows if r['brand'] == 'SUNLU']
        if not bambu or not sunlu:
            continue
        min_bambu = min(bambu, key=lambda r: compare_price_per_kg(r) or 999)
        min_sunlu = min(sunlu, key=lambda r: compare_price_per_kg(r) or 999)
        bambu_ppk = compare_price_per_kg(min_bambu) or 0
        sunlu_ppk = compare_price_per_kg(min_sunlu) or 0
        saving_pct = (bambu_ppk - sunlu_ppk) / bambu_ppk * 100 if bambu_ppk else 0
        if saving_pct >= BEAT_BRAND_PCT:
            add_deal(
                {
                    'type': 'beats_brand',
                    'score': saving_pct + 20,
                    'title': min_sunlu['product'],
                    'reason': (
                        f'SUNLU slår Bambu på {material}: €{sunlu_ppk:.2f}/kg '
                        f'vs €{bambu_ppk:.2f}/kg ({saving_pct:.0f}% billigere)'
                    ),
                    'item': min_sunlu,
                    'material': material,
                    'vs_brand': 'Bambu Lab',
                    'saving_pct': round(saving_pct, 1),
                }
            )
        elif -saving_pct >= BEAT_BRAND_PCT:
            add_deal(
                {
                    'type': 'beats_brand',
                    'score': -saving_pct + 20,
                    'title': min_bambu['product'],
                    'reason': (
                        f'Bambu slår SUNLU på {material}: €{bambu_ppk:.2f}/kg '
                        f'vs €{sunlu_ppk:.2f}/kg ({-saving_pct:.0f}% billigere)'
                    ),
                    'item': min_bambu,
                    'material': material,
                    'vs_brand': 'SUNLU',
                    'saving_pct': round(-saving_pct, 1),
                }
            )

    # Price drops vs previous snapshot.
    prev = _previous_prices(history)
    if prev:
        for row in items:
            if not is_standard_1kg(row):
                continue
            key = row_key(row)
            old = prev.get(key)
            current = effective_price(row)
            if old is None or current is None or current >= old:
                continue
            drop_pct = (old - current) / old * 100
            if drop_pct < DROP_MIN_PCT:
                continue
            add_deal(
                {
                    'type': 'price_drop',
                    'score': drop_pct + 30,
                    'title': row['product'],
                    'reason': f'Prisfald {drop_pct:.0f}%: €{old:.2f} → €{current:.2f}',
                    'item': row,
                    'old_price': old,
                    'drop_pct': round(drop_pct, 1),
                }
            )

    deals.sort(key=lambda d: d['score'], reverse=True)
    return deals[:limit]


def _previous_prices(history: dict[str, Any] | None) -> dict[str, float]:
    if not history:
        return {}
    snapshots = history.get('snapshots') or []
    if len(snapshots) < 2:
        return {}
    return snapshots[-2].get('prices', {})


def snapshot_prices(items: list[dict[str, Any]]) -> dict[str, float]:
    prices: dict[str, float] = {}
    for row in items:
        price = effective_price(row)
        if price is None:
            continue
        prices[row_key(row)] = price
    return prices


def append_history(history: dict[str, Any], items: list[dict[str, Any]], updated_at: str, *, max_snapshots: int = 14) -> dict[str, Any]:
    entry = {'at': updated_at, 'prices': snapshot_prices(items)}
    snapshots = list(history.get('snapshots') or [])
    if snapshots and snapshots[-1].get('at') == updated_at:
        snapshots[-1] = entry
    else:
        snapshots.append(entry)
    if len(snapshots) > max_snapshots:
        snapshots = snapshots[-max_snapshots:]
    return {'snapshots': snapshots}
