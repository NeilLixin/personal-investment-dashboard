from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from src.config import DATABASE_PATH, ensure_directories


SCHEMA = """
CREATE TABLE IF NOT EXISTS holdings (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, code TEXT, platform TEXT NOT NULL,
    asset_type TEXT NOT NULL, market TEXT NOT NULL, current_value REAL DEFAULT 0,
    cost_amount REAL DEFAULT 0, profit_amount REAL DEFAULT 0, profit_rate REAL DEFAULT 0,
    holding_share REAL, latest_price REAL, target_min_ratio REAL DEFAULT 0,
    target_max_ratio REAL DEFAULT 1, risk_level TEXT DEFAULT '中', note TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT, trade_date TEXT NOT NULL, asset_name TEXT NOT NULL,
    action TEXT NOT NULL, amount REAL DEFAULT 0, price REAL DEFAULT 0, reason TEXT,
    emotion TEXT, plan_id INTEGER, review_date TEXT, review_result TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT, asset_name TEXT NOT NULL, plan_type TEXT NOT NULL,
    trigger_condition TEXT, trigger_value REAL, suggested_action TEXT, priority INTEGER DEFAULT 2,
    enabled INTEGER DEFAULT 1, note TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT, rule_name TEXT NOT NULL, asset_type TEXT,
    condition_type TEXT, condition_value REAL, action_suggestion TEXT, level TEXT DEFAULT 'warning',
    enabled INTEGER DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ocr_import_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT, source_platform TEXT, image_count INTEGER DEFAULT 0,
    raw_text TEXT, parsed_json TEXT, status TEXT DEFAULT 'pending', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY, value TEXT, updated_at TEXT NOT NULL
);
"""


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


@contextmanager
def connection(db_path: Path = DATABASE_PATH):
    ensure_directories()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: Path = DATABASE_PATH) -> None:
    with connection(db_path) as conn:
        conn.executescript(SCHEMA)


def fetch_all(table: str, db_path: Path = DATABASE_PATH, order_by: str = "id DESC") -> list[dict]:
    allowed = {"holdings", "trades", "plans", "rules", "ocr_import_batches", "app_settings"}
    if table not in allowed:
        raise ValueError("Unsupported table")
    with connection(db_path) as conn:
        return [dict(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY {order_by}").fetchall()]


def get_row(table: str, row_id: int, db_path: Path = DATABASE_PATH) -> dict | None:
    if table not in {"holdings", "trades", "plans", "rules", "ocr_import_batches"}:
        raise ValueError("Unsupported table")
    with connection(db_path) as conn:
        row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (row_id,)).fetchone()
        return dict(row) if row else None


def insert_row(table: str, data: dict[str, Any], db_path: Path = DATABASE_PATH) -> int:
    payload = dict(data)
    timestamp = now_text()
    if table != "app_settings":
        payload.setdefault("created_at", timestamp)
    if table in {"holdings", "trades", "plans", "rules"}:
        payload.setdefault("updated_at", timestamp)
    columns = ", ".join(payload)
    placeholders = ", ".join("?" for _ in payload)
    with connection(db_path) as conn:
        cursor = conn.execute(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", tuple(payload.values()))
        return int(cursor.lastrowid)


def update_row(table: str, row_id: int, data: dict[str, Any], db_path: Path = DATABASE_PATH) -> None:
    payload = dict(data)
    if table in {"holdings", "trades", "plans", "rules"}:
        payload["updated_at"] = now_text()
    assignments = ", ".join(f"{key} = ?" for key in payload)
    with connection(db_path) as conn:
        conn.execute(f"UPDATE {table} SET {assignments} WHERE id = ?", (*payload.values(), row_id))


def delete_row(table: str, row_id: int, db_path: Path = DATABASE_PATH) -> None:
    with connection(db_path) as conn:
        conn.execute(f"DELETE FROM {table} WHERE id = ?", (row_id,))


def find_holding(name: str = "", code: str = "", db_path: Path = DATABASE_PATH) -> dict | None:
    with connection(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM holdings WHERE (code != '' AND code = ?) OR name = ? ORDER BY id LIMIT 1",
            (code.strip(), name.strip()),
        ).fetchone()
        return dict(row) if row else None


def get_setting(key: str, default: Any = None, db_path: Path = DATABASE_PATH) -> Any:
    with connection(db_path) as conn:
        row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    if not row:
        return default
    try:
        return json.loads(row["value"])
    except (json.JSONDecodeError, TypeError):
        return row["value"]


def set_setting(key: str, value: Any, db_path: Path = DATABASE_PATH) -> None:
    text = json.dumps(value, ensure_ascii=False)
    with connection(db_path) as conn:
        conn.execute(
            "INSERT INTO app_settings(key, value, updated_at) VALUES(?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, text, now_text()),
        )


def clear_tables(tables: Iterable[str], db_path: Path = DATABASE_PATH) -> None:
    allowed = {"holdings", "trades", "plans", "rules", "ocr_import_batches", "app_settings"}
    with connection(db_path) as conn:
        for table in tables:
            if table not in allowed:
                raise ValueError("Unsupported table")
            conn.execute(f"DELETE FROM {table}")
