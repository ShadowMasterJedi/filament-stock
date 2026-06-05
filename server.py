#!/usr/bin/env python3
"""Filament Stock – webserver med REST API og statiske filer."""

from __future__ import annotations

import argparse
import cgi
import json
import mimetypes
import re
import ssl
import subprocess
import sys
import uuid
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import db

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / 'static'
DECODE_SCRIPT = ROOT / 'decode_image.py'
CERT_PATH = ROOT / 'certs' / 'cert.pem'
KEY_PATH = ROOT / 'certs' / 'key.pem'


def json_response(handler: SimpleHTTPRequestHandler, payload, status=200):
    body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    handler.send_response(status)
    handler.send_header('Content-Type', 'application/json; charset=utf-8')
    handler.send_header('Content-Length', str(len(body)))
    handler.send_header('Cache-Control', 'no-store')
    handler.end_headers()
    handler.wfile.write(body)


def read_json(handler: SimpleHTTPRequestHandler) -> dict:
    length = int(handler.headers.get('Content-Length', 0))
    raw = handler.rfile.read(length) if length else b'{}'
    return json.loads(raw.decode('utf-8') or '{}')


def get_uploaded_file(form: cgi.FieldStorage, field_name: str = 'file'):
    if field_name not in form:
        return None
    field = form[field_name]
    if getattr(field, 'file', None) is None:
        return None
    if not getattr(field, 'filename', None):
        return None
    return field


class FilamentHandler(SimpleHTTPRequestHandler):
    extensions_map = {
        **getattr(SimpleHTTPRequestHandler, 'extensions_map', {}),
        '.wasm': 'application/wasm',
        '.gz': 'application/gzip',
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC), **kwargs)

    def log_message(self, fmt, *args):
        sys.stderr.write('%s - %s\n' % (self.address_string(), fmt % args))

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == '/api/health':
            return json_response(self, {'ok': True, 'app': 'filament-stock'})
        if path == '/api/stats':
            return json_response(self, db.get_stats())
        if path == '/api/inventory':
            return json_response(self, {'items': db.list_filaments()})
        if path == '/api/materials':
            return json_response(self, {'materials': db.MATERIALS})
        if path == '/api/bambu/stats':
            return json_response(self, {'count': db.bambu_catalog_count()})
        if path == '/api/bambu/lookup':
            qs = parse_qs(parsed.query)
            barcode = (qs.get('barcode') or [''])[0].strip()
            if not barcode:
                return json_response(self, {'error': 'Mangler stregkode'}, 400)
            match = db.lookup_bambu(barcode)
            if not match:
                return json_response(self, {'found': False, 'barcode': barcode})
            return json_response(self, {'found': True, 'product': match})

        m = re.match(r'^/api/filament/([^/]+)$', path)
        if m:
            item = db.get_filament_by_barcode(cgi.unescape(m.group(1)))
            if not item:
                return json_response(self, {'error': 'Ikke fundet'}, 404)
            photos = db.list_photos(item['id'])
            return json_response(self, {'item': item, 'photos': photos})

        m = re.match(r'^/api/photos/(\d+)/file$', path)
        if m:
            photo = db.get_photo(int(m.group(1)))
            if not photo:
                self.send_error(404)
                return
            filepath = db.PHOTOS_DIR / photo['filename']
            if not filepath.exists():
                self.send_error(404)
                return
            return self._serve_file(filepath)

        if path.startswith('/photos/'):
            filename = path.split('/photos/', 1)[1]
            if '..' in filename or '/' in filename:
                self.send_error(400)
                return
            filepath = db.PHOTOS_DIR / filename
            if filepath.exists():
                return self._serve_file(filepath)
            self.send_error(404)
            return

        if path == '/' or path == '':
            self.path = '/index.html'
        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        try:
            if path == '/api/scan':
                data = read_json(self)
                code = (data.get('barcode') or data.get('color_id') or data.get('sku') or '').strip()
                delta = int(data.get('delta', 1))
                source = data.get('source', 'scan')
                auto_register = bool(data.get('auto_register', True))
                if not code:
                    return json_response(self, {'error': 'Mangler farve-ID eller stregkode'}, 400)
                existing, bambu = db.resolve_filament_for_scan(code)
                if not existing:
                    if bambu and auto_register and delta > 0:
                        item = db.filament_from_bambu(code, bambu, quantity=0)
                        item = db.adjust_quantity(item['barcode'], delta, source=source)
                        return json_response(
                            self,
                            {
                                'known': True,
                                'item': item,
                                'bambu': bambu,
                                'auto_registered': True,
                            },
                        )
                    return json_response(
                        self,
                        {
                            'known': False,
                            'barcode': code,
                            'color_id': bambu['bambu_code'] if bambu else code,
                            'sku': bambu['bambu_code'] if bambu else code,
                            'bambu': bambu,
                        },
                    )
                item = db.adjust_quantity(existing['barcode'], delta, source=source)
                return json_response(self, {'known': True, 'item': item, 'bambu': bambu})

            if path == '/api/bambu/sync':
                import bambu_sync

                rows = bambu_sync.sync_catalog(verbose=False)
                return json_response(self, {'ok': True, 'count': len(rows)})

            if path == '/api/filament':
                data = read_json(self)
                if not data.get('barcode', '').strip():
                    return json_response(self, {'error': 'Mangler stregkode'}, 400)
                item = db.upsert_filament(data)
                return json_response(self, {'item': item})

            if path == '/api/photo':
                return self._handle_photo_upload()

            if path == '/api/decode':
                return self._handle_decode_upload()

            return json_response(self, {'error': 'Ukendt endpoint'}, 404)
        except KeyError as exc:
            return json_response(self, {'error': str(exc)}, 404)
        except (ValueError, json.JSONDecodeError) as exc:
            return json_response(self, {'error': str(exc)}, 400)

    def _handle_decode_upload(self):
        content_type = self.headers.get('Content-Type', '')
        if not content_type.startswith('multipart/form-data'):
            return json_response(self, {'error': 'Forventet multipart upload'}, 400)

        form = cgi.FieldStorage(
            fp=self.rfile,
            headers=self.headers,
            environ={
                'REQUEST_METHOD': 'POST',
                'CONTENT_TYPE': content_type,
            },
        )
        file_field = get_uploaded_file(form)
        if file_field is None:
            return json_response(self, {'error': 'Mangler fil'}, 400)

        data = file_field.file.read()
        try:
            proc = subprocess.run(
                [sys.executable, str(DECODE_SCRIPT)],
                input=data,
                capture_output=True,
                timeout=15,
                check=False,
            )
            if proc.returncode != 0:
                msg = proc.stderr.decode('utf-8', errors='ignore').strip() or 'Kunne ikke læse stregkode'
                return json_response(self, {'error': msg}, 400)
            barcode = proc.stdout.decode('utf-8', errors='ignore').strip()
            return json_response(self, {'barcode': barcode})
        except subprocess.TimeoutExpired:
            return json_response(self, {'error': 'Stregkode-læsning timeout'}, 504)
        except OSError as exc:
            return json_response(self, {'error': str(exc)}, 500)

    def _handle_photo_upload(self):
        content_type = self.headers.get('Content-Type', '')
        if not content_type.startswith('multipart/form-data'):
            return json_response(self, {'error': 'Forventet multipart upload'}, 400)

        form = cgi.FieldStorage(
            fp=self.rfile,
            headers=self.headers,
            environ={
                'REQUEST_METHOD': 'POST',
                'CONTENT_TYPE': content_type,
            },
        )

        file_field = get_uploaded_file(form)
        if file_field is None:
            return json_response(self, {'error': 'Mangler fil'}, 400)

        ext = Path(file_field.filename).suffix.lower() or '.jpg'
        if ext not in {'.jpg', '.jpeg', '.png', '.webp', '.heic'}:
            ext = '.jpg'
        filename = f'{uuid.uuid4().hex}{ext}'
        dest = db.PHOTOS_DIR / filename
        with open(dest, 'wb') as out:
            out.write(file_field.file.read())

        filament_id = form.getvalue('filament_id')
        filament_id = int(filament_id) if filament_id not in (None, '') else None
        caption = form.getvalue('caption', '') or ''
        barcode = form.getvalue('barcode', '') or ''

        if barcode and not filament_id:
            item = db.get_filament_by_barcode(barcode.strip())
            if item:
                filament_id = item['id']

        photo = db.add_photo(filament_id, filename, caption)
        return json_response(self, {'photo': photo, 'url': f'/photos/{filename}'})

    def _serve_file(self, filepath: Path):
        ctype = mimetypes.guess_type(str(filepath))[0] or 'application/octet-stream'
        data = filepath.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'public, max-age=86400')
        self.end_headers()
        self.wfile.write(data)


def build_ssl_context() -> ssl.SSLContext:
    if not CERT_PATH.exists() or not KEY_PATH.exists():
        raise FileNotFoundError(
            f'Mangler certifikat. Kør: ./gen-cert.sh  (forventet {CERT_PATH})'
        )
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(certfile=str(CERT_PATH), keyfile=str(KEY_PATH))
    return ctx


def maybe_sync_bambu_catalog() -> None:
    if db.bambu_catalog_count() > 0:
        return
    try:
        import bambu_sync

        rows = bambu_sync.sync_catalog(verbose=True)
        print(f'  Bambu katalog: {len(rows)} varianter hentet')
    except Exception as exc:
        print(f'  Bambu sync fejlede (kan køres manuelt): {exc}')


def main():
    parser = argparse.ArgumentParser(description='Filament Stock webserver')
    parser.add_argument('port', nargs='?', type=int, default=8090)
    parser.add_argument('--https', action='store_true', help='Start med TLS (self-signed cert)')
    parser.add_argument('--http', action='store_true', help='Start uden TLS')
    args = parser.parse_args()

    use_https = args.https or (not args.http and CERT_PATH.exists() and KEY_PATH.exists())

    db.init_db()
    maybe_sync_bambu_catalog()
    server = ThreadingHTTPServer(('0.0.0.0', args.port), FilamentHandler)
    scheme = 'http'
    if use_https:
        server.socket = build_ssl_context().wrap_socket(server.socket, server_side=True)
        scheme = 'https'

    print(f'Filament Stock på {scheme}://0.0.0.0:{args.port}')
    print(f'  Database: {db.DB_PATH}')
    if use_https:
        print(f'  TLS cert: {CERT_PATH}')
    else:
        print('  Uden TLS – live kamera på iPhone virker ikke over LAN')
        print('  Kør ./gen-cert.sh og start med --https')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nStopper…')
        server.server_close()


if __name__ == '__main__':
    main()
