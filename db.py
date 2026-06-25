"""SQLite database for filament inventory."""

from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / 'data'
DB_PATH = DATA_DIR / 'filament.db'
PHOTOS_DIR = DATA_DIR / 'photos'

MATERIALS = ['PLA', 'PETG', 'ABS', 'TPU', 'ASA', 'NYLON', 'PC', 'HIPS', 'PA-CF', 'PETG-CF', 'PLA-CF', 'Andet']


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)


@contextmanager
def get_db():
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with get_db() as conn:
        conn.executescript(
            '''
            CREATE TABLE IF NOT EXISTS filaments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                barcode TEXT NOT NULL UNIQUE,
                brand TEXT DEFAULT '',
                material TEXT DEFAULT 'PLA',
                color TEXT DEFAULT '',
                color_hex TEXT DEFAULT '#7a8fa8',
                weight_g INTEGER DEFAULT 1000,
                quantity INTEGER NOT NULL DEFAULT 0,
                location TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS photos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filament_id INTEGER,
                filename TEXT NOT NULL,
                caption TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY (filament_id) REFERENCES filaments(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS scan_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                barcode TEXT NOT NULL,
                filament_id INTEGER,
                delta INTEGER NOT NULL DEFAULT 1,
                source TEXT DEFAULT 'scan',
                created_at TEXT NOT NULL,
                FOREIGN KEY (filament_id) REFERENCES filaments(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS bambu_catalog (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bambu_code TEXT NOT NULL,
                store_sku TEXT NOT NULL,
                barcode TEXT DEFAULT '',
                product_line TEXT NOT NULL,
                material TEXT NOT NULL,
                color TEXT NOT NULL,
                spool_type TEXT DEFAULT '',
                weight_g INTEGER DEFAULT 1000,
                brand TEXT DEFAULT 'Bambu Lab',
                image_url TEXT DEFAULT '',
                store_url TEXT DEFAULT '',
                updated_at TEXT NOT NULL,
                UNIQUE(store_sku)
            );

            CREATE INDEX IF NOT EXISTS idx_filaments_material ON filaments(material);
            CREATE INDEX IF NOT EXISTS idx_scan_events_created ON scan_events(created_at);
            CREATE INDEX IF NOT EXISTS idx_bambu_code ON bambu_catalog(bambu_code);
            CREATE INDEX IF NOT EXISTS idx_bambu_barcode ON bambu_catalog(barcode);
            '''
        )
        _ensure_filament_bambu_columns(conn)
        _ensure_price_watch_table(conn)


def _ensure_price_watch_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        '''
        CREATE TABLE IF NOT EXISTS price_watch_state (
            filament_id INTEGER PRIMARY KEY,
            last_unit_eur REAL,
            last_ppk REAL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (filament_id) REFERENCES filaments(id) ON DELETE CASCADE
        )
        '''
    )


def _ensure_filament_bambu_columns(conn: sqlite3.Connection) -> None:
    cols = {row[1] for row in conn.execute('PRAGMA table_info(filaments)').fetchall()}
    if 'bambu_code' not in cols:
        conn.execute('ALTER TABLE filaments ADD COLUMN bambu_code TEXT DEFAULT ""')
    if 'store_sku' not in cols:
        conn.execute('ALTER TABLE filaments ADD COLUMN store_sku TEXT DEFAULT ""')


def get_price_watch(filament_id: int) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            'SELECT * FROM price_watch_state WHERE filament_id = ?',
            (filament_id,),
        ).fetchone()
        return dict(row) if row else None


def upsert_price_watch(filament_id: int, last_unit_eur: float | None, last_ppk: float | None) -> None:
    now = utc_now()
    with get_db() as conn:
        conn.execute(
            '''
            INSERT INTO price_watch_state (filament_id, last_unit_eur, last_ppk, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(filament_id) DO UPDATE SET
                last_unit_eur = excluded.last_unit_eur,
                last_ppk = excluded.last_ppk,
                updated_at = excluded.updated_at
            ''',
            (filament_id, last_unit_eur, last_ppk, now),
        )


def row_to_filament(row: sqlite3.Row, photo_count: int = 0) -> dict:
    keys = set(row.keys())
    return {
        'id': row['id'],
        'barcode': row['barcode'],
        'brand': row['brand'],
        'material': row['material'],
        'color': row['color'],
        'color_hex': row['color_hex'],
        'weight_g': row['weight_g'],
        'quantity': row['quantity'],
        'location': row['location'],
        'notes': row['notes'],
        'bambu_code': row['bambu_code'] if 'bambu_code' in keys else '',
        'store_sku': row['store_sku'] if 'store_sku' in keys else '',
        'created_at': row['created_at'],
        'updated_at': row['updated_at'],
        'photo_count': photo_count,
    }


def row_to_bambu(row: sqlite3.Row) -> dict:
    return {
        'bambu_code': row['bambu_code'],
        'store_sku': row['store_sku'],
        'barcode': row['barcode'],
        'product_line': row['product_line'],
        'material': row['material'],
        'color': row['color'],
        'spool_type': row['spool_type'],
        'weight_g': row['weight_g'],
        'brand': row['brand'],
        'image_url': row['image_url'],
        'store_url': row['store_url'],
    }


def get_filament_by_barcode(barcode: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute('SELECT * FROM filaments WHERE barcode = ?', (barcode,)).fetchone()
        if not row:
            return None
        count = conn.execute(
            'SELECT COUNT(*) AS c FROM photos WHERE filament_id = ?', (row['id'],)
        ).fetchone()['c']
        return row_to_filament(row, count)


def get_filament_by_bambu_code(bambu_code: str) -> dict | None:
    code = bambu_code.strip()
    if not code:
        return None
    with get_db() as conn:
        row = conn.execute(
            '''
            SELECT * FROM filaments
            WHERE bambu_code = ?
            ORDER BY updated_at DESC
            LIMIT 1
            ''',
            (code,),
        ).fetchone()
        if not row:
            return None
        count = conn.execute(
            'SELECT COUNT(*) AS c FROM photos WHERE filament_id = ?', (row['id'],)
        ).fetchone()['c']
        return row_to_filament(row, count)


def resolve_filament_for_scan(code: str) -> tuple[dict | None, dict | None]:
    """Find lagerpost via stregkode, SKU eller Bambu-katalog."""
    value = code.strip()
    if not value:
        return None, None

    item = get_filament_by_barcode(value)
    if item:
        return item, None

    item = get_filament_by_bambu_code(value)
    if item:
        return item, None

    bambu = lookup_bambu(value)
    if bambu:
        item = get_filament_by_bambu_code(bambu['bambu_code'])
        if item:
            return item, bambu
        return None, bambu

    return None, None


def get_filament(filament_id: int) -> dict | None:
    with get_db() as conn:
        row = conn.execute('SELECT * FROM filaments WHERE id = ?', (filament_id,)).fetchone()
        if not row:
            return None
        count = conn.execute(
            'SELECT COUNT(*) AS c FROM photos WHERE filament_id = ?', (filament_id,)
        ).fetchone()['c']
        return row_to_filament(row, count)


def list_filaments() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            '''
            SELECT f.*, COUNT(p.id) AS photo_count
            FROM filaments f
            LEFT JOIN photos p ON p.filament_id = f.id
            GROUP BY f.id
            ORDER BY f.material, f.color, f.brand
            '''
        ).fetchall()
        return [row_to_filament(r, r['photo_count']) for r in rows]


def get_stats() -> dict:
    with get_db() as conn:
        total_spools = conn.execute(
            'SELECT COALESCE(SUM(quantity), 0) AS n FROM filaments'
        ).fetchone()['n']
        sku_count = conn.execute('SELECT COUNT(*) AS n FROM filaments').fetchone()['n']
        by_material = [
            dict(r)
            for r in conn.execute(
                '''
                SELECT material, SUM(quantity) AS spools, COUNT(*) AS skus
                FROM filaments
                GROUP BY material
                ORDER BY spools DESC
                '''
            ).fetchall()
        ]
        recent = [
            dict(r)
            for r in conn.execute(
                '''
                SELECT s.barcode, s.delta, s.created_at, f.brand, f.material, f.color
                FROM scan_events s
                LEFT JOIN filaments f ON f.id = s.filament_id
                ORDER BY s.id DESC
                LIMIT 10
                '''
            ).fetchall()
        ]
        return {
            'total_spools': total_spools,
            'sku_count': sku_count,
            'by_material': by_material,
            'recent_scans': recent,
        }


def upsert_filament(data: dict) -> dict:
    now = utc_now()
    barcode = data['barcode'].strip()
    with get_db() as conn:
        existing = conn.execute('SELECT id FROM filaments WHERE barcode = ?', (barcode,)).fetchone()
        fields = {
            'brand': data.get('brand', '').strip(),
            'material': data.get('material', 'PLA').strip() or 'PLA',
            'color': data.get('color', '').strip(),
            'color_hex': data.get('color_hex', '#7a8fa8').strip() or '#7a8fa8',
            'weight_g': int(data.get('weight_g') or 1000),
            'quantity': int(data.get('quantity') or 0),
            'location': data.get('location', '').strip(),
            'notes': data.get('notes', '').strip(),
            'bambu_code': data.get('bambu_code', '').strip(),
            'store_sku': data.get('store_sku', '').strip(),
            'updated_at': now,
        }
        if existing:
            conn.execute(
                '''
                UPDATE filaments SET
                    brand=?, material=?, color=?, color_hex=?, weight_g=?,
                    quantity=?, location=?, notes=?, bambu_code=?, store_sku=?, updated_at=?
                WHERE barcode=?
                ''',
                (
                    fields['brand'], fields['material'], fields['color'], fields['color_hex'],
                    fields['weight_g'], fields['quantity'], fields['location'], fields['notes'],
                    fields['bambu_code'], fields['store_sku'], fields['updated_at'], barcode,
                ),
            )
        else:
            conn.execute(
                '''
                INSERT INTO filaments (
                    barcode, brand, material, color, color_hex, weight_g,
                    quantity, location, notes, bambu_code, store_sku, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    barcode, fields['brand'], fields['material'], fields['color'],
                    fields['color_hex'], fields['weight_g'], fields['quantity'],
                    fields['location'], fields['notes'], fields['bambu_code'], fields['store_sku'],
                    now, now,
                ),
            )
    return get_filament_by_barcode(barcode)


def replace_bambu_catalog(rows: list[dict]) -> int:
    now = utc_now()
    with get_db() as conn:
        conn.execute('DELETE FROM bambu_catalog')
        for row in rows:
            conn.execute(
                '''
                INSERT INTO bambu_catalog (
                    bambu_code, store_sku, barcode, product_line, material, color,
                    spool_type, weight_g, brand, image_url, store_url, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    row['bambu_code'], row['store_sku'], row.get('barcode', ''),
                    row['product_line'], row['material'], row['color'], row['spool_type'],
                    int(row.get('weight_g') or 1000), row.get('brand', 'Bambu Lab'),
                    row.get('image_url', ''), row.get('store_url', ''), now,
                ),
            )
    return len(rows)


def bambu_catalog_count() -> int:
    with get_db() as conn:
        return conn.execute('SELECT COUNT(*) AS n FROM bambu_catalog').fetchone()['n']


def lookup_bambu(barcode: str) -> dict | None:
    code = barcode.strip()
    if not code:
        return None
    with get_db() as conn:
        row = conn.execute(
            'SELECT * FROM bambu_catalog WHERE barcode = ? LIMIT 1', (code,)
        ).fetchone()
        if row:
            return row_to_bambu(row)
        if re.fullmatch(r'\d{5}', code):
            row = conn.execute(
                '''
                SELECT * FROM bambu_catalog
                WHERE bambu_code = ?
                ORDER BY CASE WHEN spool_type LIKE '%spool%' THEN 0 ELSE 1 END, id
                LIMIT 1
                ''',
                (code,),
            ).fetchone()
            if row:
                return row_to_bambu(row)
    return None


def storage_barcode_for(code: str, bambu: dict | None = None) -> str:
    if bambu:
        return (bambu.get('barcode') or bambu.get('bambu_code') or code).strip()
    return code.strip()


def filament_from_bambu(barcode: str, bambu: dict, quantity: int = 1) -> dict:
    label = f"{bambu['product_line']} · {bambu['color']}"
    if bambu.get('spool_type'):
        label = f"{label} ({bambu['spool_type']})"
    storage_barcode = storage_barcode_for(barcode, bambu)
    return upsert_filament(
        {
            'barcode': storage_barcode,
            'brand': bambu.get('brand', 'Bambu Lab'),
            'material': bambu.get('material', 'PLA'),
            'color': bambu.get('color', ''),
            'color_hex': '#7a8fa8',
            'weight_g': bambu.get('weight_g', 1000),
            'quantity': quantity,
            'location': '',
            'notes': label,
            'bambu_code': bambu.get('bambu_code', ''),
            'store_sku': bambu.get('store_sku', ''),
        }
    )


def filament_from_color_id(color_id: str, quantity: int = 1) -> dict:
    code = color_id.strip()
    bambu = lookup_bambu(code)
    if bambu:
        return filament_from_bambu(code, bambu, quantity)
    return upsert_filament(
        {
            'barcode': code,
            'brand': 'Bambu Lab',
            'material': 'PLA',
            'color': '',
            'color_hex': '#7a8fa8',
            'weight_g': 1000,
            'quantity': quantity,
            'location': '',
            'notes': f'Farve-ID {code}',
            'bambu_code': code,
            'store_sku': '',
        }
    )


def adjust_quantity(barcode: str, delta: int, source: str = 'scan') -> dict:
    now = utc_now()
    with get_db() as conn:
        row = conn.execute('SELECT * FROM filaments WHERE barcode = ?', (barcode,)).fetchone()
        if not row:
            raise KeyError('Ukendt stregkode')
        new_qty = max(0, row['quantity'] + delta)
        conn.execute(
            'UPDATE filaments SET quantity = ?, updated_at = ? WHERE id = ?',
            (new_qty, now, row['id']),
        )
        conn.execute(
            '''
            INSERT INTO scan_events (barcode, filament_id, delta, source, created_at)
            VALUES (?, ?, ?, ?, ?)
            ''',
            (barcode, row['id'], delta, source, now),
        )
    return get_filament_by_barcode(barcode)


def add_photo(filament_id: int | None, filename: str, caption: str = '') -> dict:
    now = utc_now()
    with get_db() as conn:
        cur = conn.execute(
            '''
            INSERT INTO photos (filament_id, filename, caption, created_at)
            VALUES (?, ?, ?, ?)
            ''',
            (filament_id, filename, caption, now),
        )
        photo_id = cur.lastrowid
        row = conn.execute('SELECT * FROM photos WHERE id = ?', (photo_id,)).fetchone()
        return dict(row)


def list_photos(filament_id: int | None = None) -> list[dict]:
    with get_db() as conn:
        if filament_id:
            rows = conn.execute(
                'SELECT * FROM photos WHERE filament_id = ? ORDER BY id DESC', (filament_id,)
            ).fetchall()
        else:
            rows = conn.execute('SELECT * FROM photos ORDER BY id DESC LIMIT 50').fetchall()
        return [dict(r) for r in rows]


def get_photo(photo_id: int) -> dict | None:
    with get_db() as conn:
        row = conn.execute('SELECT * FROM photos WHERE id = ?', (photo_id,)).fetchone()
        return dict(row) if row else None
