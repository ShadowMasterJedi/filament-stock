"""SQLite database for filament inventory."""

from __future__ import annotations

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

            CREATE INDEX IF NOT EXISTS idx_filaments_material ON filaments(material);
            CREATE INDEX IF NOT EXISTS idx_scan_events_created ON scan_events(created_at);
            '''
        )


def row_to_filament(row: sqlite3.Row, photo_count: int = 0) -> dict:
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
        'created_at': row['created_at'],
        'updated_at': row['updated_at'],
        'photo_count': photo_count,
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
            'updated_at': now,
        }
        if existing:
            conn.execute(
                '''
                UPDATE filaments SET
                    brand=?, material=?, color=?, color_hex=?, weight_g=?,
                    quantity=?, location=?, notes=?, updated_at=?
                WHERE barcode=?
                ''',
                (
                    fields['brand'], fields['material'], fields['color'], fields['color_hex'],
                    fields['weight_g'], fields['quantity'], fields['location'], fields['notes'],
                    fields['updated_at'], barcode,
                ),
            )
        else:
            conn.execute(
                '''
                INSERT INTO filaments (
                    barcode, brand, material, color, color_hex, weight_g,
                    quantity, location, notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    barcode, fields['brand'], fields['material'], fields['color'],
                    fields['color_hex'], fields['weight_g'], fields['quantity'],
                    fields['location'], fields['notes'], now, now,
                ),
            )
    return get_filament_by_barcode(barcode)


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
