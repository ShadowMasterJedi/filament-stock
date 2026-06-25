#!/usr/bin/env python3
"""Filament price scraper – local web UI and JSON API."""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import threading
import urllib.parse
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent
STATIC = ROOT / 'static'
SHARED_UI = REPO_ROOT / 'shared' / 'ui'

sys.path.insert(0, str(REPO_ROOT))
import app_urls  # noqa: E402
CACHE_PATH = ROOT / 'data' / 'prices_cache.json'
SCRAPE_SCRIPT = ROOT / 'scrape.py'

_LOCAL_HOSTS = frozenset({'localhost', '127.0.0.1', '::1', '[::1]'})
_refresh_lock = threading.Lock()
_refresh_running = False


def lan_ip() -> str | None:
    """Best-effort LAN IPv4 for QR codes when the browser uses localhost."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(('8.8.8.8', 80))
            return sock.getsockname()[0]
    except OSError:
        pass
    try:
        name = socket.gethostname()
        for info in socket.getaddrinfo(name, None, socket.AF_INET):
            addr = info[4][0]
            if not addr.startswith('127.'):
                return addr
    except OSError:
        pass
    return None


def page_url_for(handler: SimpleHTTPRequestHandler) -> str:
    host_hdr = handler.headers.get('Host', '')
    if ':' in host_hdr:
        host, port_s = host_hdr.rsplit(':', 1)
        try:
            port = int(port_s)
        except ValueError:
            port = handler.server.server_address[1]
    else:
        host = host_hdr
        port = handler.server.server_address[1]

    host = (host or 'localhost').strip('[]')
    if host.lower() in _LOCAL_HOSTS:
        lip = lan_ip()
        if lip:
            host = lip

    return f'http://{host}:{port}'


def fetch_qr_png(target_url: str, size: int = 160) -> bytes:
    api = (
        'https://api.qrserver.com/v1/create-qr-code/?'
        f'size={size}x{size}&data={urllib.parse.quote(target_url, safe="")}'
    )
    req = urllib.request.Request(api, headers={'User-Agent': 'FilamentScraper/1.0'})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read()


def load_cache() -> dict:
    if not CACHE_PATH.exists():
        return {'updated_at': None, 'count': 0, 'errors': [], 'items': []}
    return json.loads(CACHE_PATH.read_text(encoding='utf-8'))


def json_response(handler: SimpleHTTPRequestHandler, payload, status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    handler.send_response(status)
    handler.send_header('Content-Type', 'application/json; charset=utf-8')
    handler.send_header('Content-Length', str(len(body)))
    handler.send_header('Cache-Control', 'no-store')
    handler.end_headers()
    handler.wfile.write(body)


def start_refresh() -> dict:
    global _refresh_running
    with _refresh_lock:
        if _refresh_running:
            return {'ok': True, 'status': 'running'}
        _refresh_running = True

    def worker() -> None:
        global _refresh_running
        try:
            subprocess.run(
                [sys.executable, str(SCRAPE_SCRIPT), '--quiet'],
                cwd=str(ROOT),
                check=False,
                timeout=600,
            )
        finally:
            with _refresh_lock:
                _refresh_running = False

    threading.Thread(target=worker, daemon=True).start()
    return {'ok': True, 'status': 'started'}


class PriceHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC), **kwargs)

    def log_message(self, fmt, *args):
        sys.stderr.write('%s - %s\n' % (self.address_string(), fmt % args))

    def _serve_shared_file(self, filepath: Path) -> None:
        import mimetypes

        ctype = mimetypes.guess_type(str(filepath))[0] or 'application/octet-stream'
        data = filepath.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'public, max-age=3600')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/api/health':
            return json_response(self, {'ok': True, 'app': 'filamentscraper'})
        if path == '/css/nxgenlab.css':
            css_path = SHARED_UI / 'nxgenlab.css'
            if css_path.exists():
                return self._serve_shared_file(css_path)
            self.send_error(404)
            return
        if path == '/api/info':
            page_url = page_url_for(self)
            lip = lan_ip()
            return json_response(self, {
                'page_url': page_url,
                'scraper_url': page_url,
                'stock_url': app_urls.stock_url(self),
                'lan_ip': lip,
                'port': self.server.server_address[1],
                'qr_hint': 'Telefonen skal være på samme WiFi som denne PC',
            })
        if path == '/api/qr':
            qs = parse_qs(urlparse(self.path).query)
            try:
                size = int(qs.get('size', ['160'])[0])
            except ValueError:
                size = 160
            size = max(96, min(size, 320))
            target = qs.get('url', [None])[0] or page_url_for(self)
            try:
                png = fetch_qr_png(target, size=size)
            except OSError as exc:
                return json_response(self, {'error': str(exc)}, status=502)
            self.send_response(200)
            self.send_header('Content-Type', 'image/png')
            self.send_header('Content-Length', str(len(png)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(png)
            return
        if path == '/api/prices':
            cache = load_cache()
            cache['refresh_running'] = _refresh_running
            return json_response(self, cache)
        if path == '/api/refresh':
            return json_response(self, start_refresh())
        if path in ('/', '/index.html'):
            self.path = '/index.html'
        return super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        if path == '/api/refresh':
            return json_response(self, start_refresh())
        return json_response(self, {'error': 'not found'}, status=404)


def main() -> int:
    parser = argparse.ArgumentParser(description='Filament price scraper web server')
    parser.add_argument('port', nargs='?', type=int, default=8095)
    parser.add_argument('--host', default='0.0.0.0')
    args = parser.parse_args()

    if not CACHE_PATH.exists():
        print('No cache yet – run ./scrape.sh or press Refresh in the UI', file=sys.stderr)

    server = ThreadingHTTPServer((args.host, args.port), PriceHandler)
    lip = lan_ip()
    print(f'FilamentScraper on http://{args.host}:{args.port}')
    if lip:
        print(f'  LAN (til telefon/QR): http://{lip}:{args.port}')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nStopped')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
