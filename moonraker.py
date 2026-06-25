"""Moonraker integration — auto −1 spole when print completes."""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import db

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / 'data' / 'config.json'
DEFAULT_MOONRAKER_URL = 'http://127.0.0.1:7125'
POLL_INTERVAL_S = 5.0

_lock = threading.Lock()
_last_state: str | None = None
_last_error: str | None = None
_last_decrement_at: str | None = None
_last_filename: str | None = None
_running = False


def _default_config() -> dict[str, Any]:
    return {
        'moonraker': {
            'url': DEFAULT_MOONRAKER_URL,
            'enabled': False,
            'active_barcode': '',
            'auto_decrement': True,
        }
    }


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return _default_config()
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, OSError):
        return _default_config()
    base = _default_config()
    moon = data.get('moonraker') if isinstance(data, dict) else {}
    if isinstance(moon, dict):
        base['moonraker'].update(moon)
    return base


def save_config(data: dict[str, Any]) -> dict[str, Any]:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    current = load_config()
    moon = data.get('moonraker', data)
    if isinstance(moon, dict):
        current['moonraker'].update(moon)
    CONFIG_PATH.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding='utf-8')
    return current


def moonraker_settings() -> dict[str, Any]:
    return load_config().get('moonraker', _default_config()['moonraker'])


def _moonraker_get(url: str, path: str, timeout: float = 4.0) -> dict[str, Any]:
    base = url.rstrip('/')
    req = urllib.request.Request(
        f'{base}{path}',
        headers={'Accept': 'application/json', 'User-Agent': 'FilamentStock/1.0'},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode('utf-8'))


def fetch_print_stats(url: str) -> dict[str, Any]:
    payload = _moonraker_get(
        url,
        '/printer/objects/query?print_stats&virtual_sdcard',
    )
    status = (payload.get('result') or {}).get('status') or {}
    print_stats = status.get('print_stats') or {}
    vcard = status.get('virtual_sdcard') or {}
    return {
        'state': print_stats.get('state') or 'unknown',
        'filename': print_stats.get('filename') or vcard.get('file_path') or '',
        'print_duration': print_stats.get('print_duration'),
        'total_duration': print_stats.get('total_duration'),
    }


def get_status() -> dict[str, Any]:
    settings = moonraker_settings()
    url = (settings.get('url') or DEFAULT_MOONRAKER_URL).strip()
    active = settings.get('active_barcode', '')
    active_item = db.get_filament_by_barcode(active) if active else None

    out: dict[str, Any] = {
        'ok': True,
        'enabled': bool(settings.get('enabled')),
        'auto_decrement': bool(settings.get('auto_decrement', True)),
        'url': url,
        'active_barcode': active,
        'active_item': None,
        'connected': False,
        'print_state': None,
        'filename': None,
        'last_decrement_at': _last_decrement_at,
        'last_error': _last_error,
    }
    if active_item:
        out['active_item'] = {
            'barcode': active_item['barcode'],
            'brand': active_item.get('brand', ''),
            'material': active_item.get('material', ''),
            'color': active_item.get('color', ''),
            'quantity': active_item.get('quantity', 0),
        }

    if not settings.get('enabled'):
        return out

    try:
        stats = fetch_print_stats(url)
        out['connected'] = True
        out['print_state'] = stats['state']
        out['filename'] = stats.get('filename') or None
        out['last_error'] = None
    except (urllib.error.URLError, json.JSONDecodeError, OSError, TimeoutError) as exc:
        out['last_error'] = str(exc)
    return out


def _handle_state_transition(prev_state: str | None, new_state: str, settings: dict[str, Any]) -> None:
    global _last_decrement_at, _last_filename

    if not settings.get('auto_decrement', True):
        return
    barcode = (settings.get('active_barcode') or '').strip()
    if not barcode:
        return
    if prev_state not in ('printing', 'paused') or new_state != 'complete':
        return

    try:
        item = db.adjust_quantity(barcode, -1, source='moonraker')
        _last_decrement_at = item.get('updated_at')
        print(f'[moonraker] Print færdig — {barcode} nu {item.get("quantity")} spoler')
    except KeyError:
        print(f'[moonraker] Ukendt aktiv spole: {barcode}')


def poll_once() -> None:
    global _last_state, _last_error, _last_filename

    settings = moonraker_settings()
    if not settings.get('enabled'):
        _last_state = None
        return

    url = (settings.get('url') or DEFAULT_MOONRAKER_URL).strip()
    try:
        stats = fetch_print_stats(url)
        state = stats.get('state') or 'unknown'
        _last_error = None
        _last_filename = stats.get('filename') or None
        with _lock:
            prev = _last_state
            _handle_state_transition(prev, state, settings)
            _last_state = state
    except (urllib.error.URLError, json.JSONDecodeError, OSError, TimeoutError) as exc:
        _last_error = str(exc)


def _watch_loop() -> None:
    global _running
    while _running:
        try:
            poll_once()
        except Exception as exc:
            print(f'[moonraker] poll fejl: {exc}')
        time.sleep(POLL_INTERVAL_S)


def start_watcher() -> None:
    global _running
    if _running:
        return
    _running = True
    thread = threading.Thread(target=_watch_loop, name='moonraker-watcher', daemon=True)
    thread.start()
    print('[moonraker] Watcher startet')


def stop_watcher() -> None:
    global _running
    _running = False
