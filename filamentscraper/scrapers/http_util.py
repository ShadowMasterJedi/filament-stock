"""Shared HTTP helpers for store scrapers."""

from __future__ import annotations

import time
import urllib.error
import urllib.request

USER_AGENT = 'FilamentScraper/1.0 (+local price compare)'


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
                time.sleep(1.5 * (attempt + 1))
                continue
            raise
    if last_err:
        raise last_err
    raise RuntimeError('fetch failed')


def fetch_json(url: str, timeout: int = 30, retries: int = 4) -> object:
    import json

    return json.loads(fetch(url, timeout=timeout, retries=retries))
