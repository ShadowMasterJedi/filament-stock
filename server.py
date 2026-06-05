#!/usr/bin/env python3
"""Filament Stock – webserver med REST API og statiske filer."""

from __future__ import annotations

import cgi
import json
import mimetypes
import re
import sys
import uuid
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import db

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / 'static'


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


class FilamentHandler(SimpleHTTPRequestHandler):
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
                barcode = (data.get('barcode') or '').strip()
                delta = int(data.get('delta', 1))
                source = data.get('source', 'scan')
                if not barcode:
                    return json_response(self, {'error': 'Mangler stregkode'}, 400)
                existing = db.get_filament_by_barcode(barcode)
                if not existing:
                    return json_response(self, {'known': False, 'barcode': barcode})
                item = db.adjust_quantity(barcode, delta, source=source)
                return json_response(self, {'known': True, 'item': item})

            if path == '/api/filament':
                data = read_json(self)
                if not data.get('barcode', '').strip():
                    return json_response(self, {'error': 'Mangler stregkode'}, 400)
                item = db.upsert_filament(data)
                return json_response(self, {'item': item})

            if path == '/api/photo':
                return self._handle_photo_upload()

            return json_response(self, {'error': 'Ukendt endpoint'}, 404)
        except KeyError as exc:
            return json_response(self, {'error': str(exc)}, 404)
        except (ValueError, json.JSONDecodeError) as exc:
            return json_response(self, {'error': str(exc)}, 400)

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

        file_field = form['file'] if 'file' in form else None
        if not file_field or not getattr(file_field, 'file', None) or not file_field.filename:
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


def main():
    db.init_db()
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8090
    server = ThreadingHTTPServer(('0.0.0.0', port), FilamentHandler)
    print(f'Filament Stock på port {port}')
    print(f'  Database: {db.DB_PATH}')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nStopper…')
        server.server_close()


if __name__ == '__main__':
    main()
