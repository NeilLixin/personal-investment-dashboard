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
    target_max_ratio REAL DEFAULT 1, risk_level TEXT DEFAULT '中', daily_profit REAL, note TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT, trade_date TEXT NOT NULL, asset_name TEXT NOT NULL,
    action TEXT NOT NULL, amount REAL DEFAULT 0, price REAL DEFAULT 0, reason TEXT,
    emotion TEXT, plan_id INTEGER, review_date TEXT, review_result TEXT,
    is_planned INTEGER DEFAULT 0, review_status TEXT DEFAULT 'pending',
    result_type TEXT DEFAULT '未判断', result_amount REAL, result_rate REAL,
    mistake_tags TEXT DEFAULT '[]', success_tags TEXT DEFAULT '[]', lesson TEXT,
    confidence_score INTEGER, discipline_score INTEGER,
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
CREATE TABLE IF NOT EXISTS market_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT, holding_id INTEGER, platform TEXT, code TEXT, name TEXT,
    asset_type TEXT, source TEXT NOT NULL, source_name TEXT, snapshot_date TEXT NOT NULL,
    fetched_at TEXT NOT NULL, price REAL, previous_price REAL, nav REAL, previous_nav REAL,
    change_pct REAL, change_amount REAL, daily_pnl REAL, daily_pnl_estimated INTEGER DEFAULT 0,
    holding_pnl REAL, holding_return_pct REAL, market_value REAL, shares REAL,
    currency TEXT DEFAULT 'CNY', status TEXT, quality_level TEXT, raw_payload TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_market_snapshot_unique
    ON market_snapshots(holding_id, snapshot_date, source);
CREATE INDEX IF NOT EXISTS idx_market_snapshot_latest
    ON market_snapshots(holding_id, snapshot_date DESC, fetched_at DESC);
CREATE TABLE IF NOT EXISTS market_refresh_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT, source_name TEXT, started_at TEXT,
    finished_at TEXT, status TEXT, total_holdings INTEGER DEFAULT 0, success_count INTEGER DEFAULT 0,
    failed_count INTEGER DEFAULT 0, skipped_count INTEGER DEFAULT 0, message TEXT, error TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS screenshot_profit_import_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT, source_name TEXT, uploaded_file_count INTEGER DEFAULT 0,
    ocr_engine TEXT, status TEXT, raw_text TEXT, parsed_count INTEGER DEFAULT 0,
    matched_count INTEGER DEFAULT 0, unmatched_count INTEGER DEFAULT 0, confirmed_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fund_code_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT NOT NULL, short_name TEXT, full_name TEXT,
    fund_type TEXT, market_type TEXT, source TEXT, source_name TEXT NOT NULL,
    updated_at TEXT NOT NULL, raw_payload TEXT,
    UNIQUE(code, source_name)
);
CREATE TABLE IF NOT EXISTS fund_code_match_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, holding_id INTEGER, holding_name TEXT, normalized_name TEXT,
    matched_code TEXT, matched_name TEXT, confidence REAL, match_status TEXT,
    candidates_json TEXT, confirmed INTEGER DEFAULT 0, created_at TEXT NOT NULL
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
        columns = {row[1] for row in conn.execute("PRAGMA table_info(trades)")}
        migrations = {
            "is_planned": "INTEGER DEFAULT 0", "review_status": "TEXT DEFAULT 'pending'",
            "result_type": "TEXT DEFAULT '未判断'", "result_amount": "REAL", "result_rate": "REAL",
            "mistake_tags": "TEXT DEFAULT '[]'", "success_tags": "TEXT DEFAULT '[]'", "lesson": "TEXT",
            "confidence_score": "INTEGER", "discipline_score": "INTEGER",
            "quantity": "REAL", "note": "TEXT",
        }
        for name, definition in migrations.items():
            if name not in columns:
                conn.execute(f"ALTER TABLE trades ADD COLUMN {name} {definition}")
        holding_columns = {row[1] for row in conn.execute("PRAGMA table_info(holdings)")}
        if "daily_profit" not in holding_columns:
            conn.execute("ALTER TABLE holdings ADD COLUMN daily_profit REAL")


def fetch_all(table: str, db_path: Path = DATABASE_PATH, order_by: str = "id DESC") -> list[dict]:
    allowed = {"holdings", "trades", "plans", "rules", "ocr_import_batches", "app_settings",
               "market_snapshots", "market_refresh_logs", "screenshot_profit_import_batches", "fund_code_candidates", "fund_code_match_logs"}
    if table not in allowed:
        raise ValueError("Unsupported table")
    with connection(db_path) as conn:
        return [dict(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY {order_by}").fetchall()]


def get_row(table: str, row_id: int, db_path: Path = DATABASE_PATH) -> dict | None:
    if table not in {"holdings", "trades", "plans", "rules", "ocr_import_batches", "market_snapshots",
                     "market_refresh_logs", "screenshot_profit_import_batches", "fund_code_candidates", "fund_code_match_logs"}:
        raise ValueError("Unsupported table")
    with connection(db_path) as conn:
        row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (row_id,)).fetchone()
        return dict(row) if row else None


def insert_row(table: str, data: dict[str, Any], db_path: Path = DATABASE_PATH) -> int:
    payload = dict(data)
    timestamp = now_text()
    if table != "app_settings":
        payload.setdefault("created_at", timestamp)
    if table in {"holdings", "trades", "plans", "rules", "market_snapshots", "screenshot_profit_import_batches"}:
        payload.setdefault("updated_at", timestamp)
    columns = ", ".join(payload)
    placeholders = ", ".join("?" for _ in payload)
    with connection(db_path) as conn:
        cursor = conn.execute(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", tuple(payload.values()))
        return int(cursor.lastrowid)


def update_row(table: str, row_id: int, data: dict[str, Any], db_path: Path = DATABASE_PATH) -> None:
    payload = dict(data)
    if table in {"holdings", "trades", "plans", "rules", "market_snapshots", "screenshot_profit_import_batches"}:
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
    allowed = {"holdings", "trades", "plans", "rules", "ocr_import_batches", "app_settings",
               "market_snapshots", "market_refresh_logs", "screenshot_profit_import_batches", "fund_code_candidates", "fund_code_match_logs"}
    with connection(db_path) as conn:
        for table in tables:
            if table not in allowed:
                raise ValueError("Unsupported table")
            conn.execute(f"DELETE FROM {table}")
