#!/usr/bin/env python3
"""Fetch filament prices from Bambu Lab and SUNLU, save local cache."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from scrapers import scrape_bambu, scrape_sunlu
from scrapers.deals import append_history, compute_deals, compute_max_discount_buys, enrich_item

ROOT = Path(__file__).resolve().parent
CACHE_PATH = ROOT / 'data' / 'prices_cache.json'
HISTORY_PATH = ROOT / 'data' / 'price_history.json'


def load_cache() -> dict:
    if not CACHE_PATH.exists():
        return {}
    return json.loads(CACHE_PATH.read_text(encoding='utf-8'))


def save_cache(payload: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')


def load_history() -> dict:
    if not HISTORY_PATH.exists():
        return {'snapshots': []}
    return json.loads(HISTORY_PATH.read_text(encoding='utf-8'))


def save_history(history: dict) -> None:
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding='utf-8')


def run_scrape(
    *,
    bambu: bool = True,
    sunlu: bool = True,
    verbose: bool = True,
    bambu_max: int | None = None,
) -> dict:
    rows: list[dict] = []
    errors: list[str] = []

    if sunlu:
        try:
            rows.extend(scrape_sunlu(verbose=verbose))
        except Exception as exc:
            errors.append(f'sunlu: {exc}')
            if verbose:
                print(f'[sunlu] failed: {exc}', file=sys.stderr)

    if bambu:
        try:
            rows.extend(scrape_bambu(verbose=verbose, max_products=bambu_max))
        except Exception as exc:
            errors.append(f'bambu: {exc}')
            if verbose:
                print(f'[bambu] failed: {exc}', file=sys.stderr)

    if not rows:
        cached = load_cache()
        if cached.get('items'):
            if verbose:
                print('Using previous cache (scrape returned no data)', file=sys.stderr)
            return cached
        raise RuntimeError('No price data scraped')

    updated_at = datetime.now(timezone.utc).isoformat()
    rows = [enrich_item(dict(row)) for row in rows]
    history = load_history()
    deals = compute_deals(rows, history)
    max_discount_buys = compute_max_discount_buys(rows)
    history = append_history(history, rows, updated_at)

    payload = {
        'updated_at': updated_at,
        'count': len(rows),
        'deal_count': len(deals),
        'max_discount_count': len(max_discount_buys),
        'errors': errors,
        'deals': deals,
        'max_discount_buys': max_discount_buys,
        'items': rows,
    }
    save_cache(payload)
    save_history(history)
    if verbose:
        brands = {}
        for row in rows:
            brands[row['brand']] = brands.get(row['brand'], 0) + 1
        print(f'Saved {len(rows)} rows: {brands}')
        print(f'Found {len(deals)} good deals, {len(max_discount_buys)} max-rabat køb')
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description='Scrape filament store prices')
    parser.add_argument('--bambu-only', action='store_true')
    parser.add_argument('--sunlu-only', action='store_true')
    parser.add_argument('--quiet', action='store_true')
    parser.add_argument('--bambu-max', type=int, default=None, help='Limit Bambu product pages (debug)')
    args = parser.parse_args()

    bambu = not args.sunlu_only
    sunlu = not args.bambu_only
    try:
        run_scrape(bambu=bambu, sunlu=sunlu, verbose=not args.quiet, bambu_max=args.bambu_max)
        return 0
    except Exception as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
