"""LAN URLs for NxGenLab Filament apps (Stock HTTPS, Scraper HTTP)."""

from __future__ import annotations

import socket
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler

_LOCAL_HOSTS = frozenset({'localhost', '127.0.0.1', '::1', '[::1]'})
STOCK_PORT = 8090
SCRAPER_PORT = 8095


def lan_ip() -> str | None:
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


def _host_from_request(handler: BaseHTTPRequestHandler) -> tuple[str, int]:
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
    return host, port


def page_url_for(
    handler: BaseHTTPRequestHandler,
    *,
    scheme: str,
    default_port: int | None = None,
) -> str:
    host, port = _host_from_request(handler)
    if default_port is not None:
        port = default_port
    if host.lower() in _LOCAL_HOSTS:
        lip = lan_ip()
        if lip:
            host = lip
    return f'{scheme}://{host}:{port}'


def stock_url(handler: BaseHTTPRequestHandler | None = None) -> str:
    if handler is not None:
        return page_url_for(handler, scheme='https', default_port=STOCK_PORT)
    host = lan_ip() or 'localhost'
    return f'https://{host}:{STOCK_PORT}'


def scraper_url(handler: BaseHTTPRequestHandler | None = None) -> str:
    if handler is not None:
        return page_url_for(handler, scheme='http', default_port=SCRAPER_PORT)
    host = lan_ip() or 'localhost'
    return f'http://{host}:{SCRAPER_PORT}'


def fetch_qr_png(target_url: str, size: int = 160) -> bytes:
    api = (
        'https://api.qrserver.com/v1/create-qr-code/?'
        f'size={size}x{size}&data={urllib.parse.quote(target_url, safe="")}'
    )
    req = urllib.request.Request(api, headers={'User-Agent': 'NxGenLab-Filament/1.0'})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read()
