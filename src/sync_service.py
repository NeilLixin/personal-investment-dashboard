from __future__ import annotations

import json
import os
import platform
import shutil
import socket
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from src.config import APP_VERSION, BACKUPS_DIR, BASE_DIR, DATABASE_PATH, SYNC_FILE, ensure_directories
from src.database import init_db

SYNC_TABLES = ("holdings", "trades", "plans", "rules", "app_settings")
REQUIRED_KEYS = {"schema_version", "exported_at", "holdings", "trades", "plans", "rules", "app_settings"}


def _rows(conn: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    return [dict(row) for row in conn.execute(f"SELECT * FROM {table}").fetchall()]


def _load_snapshot(path: Path) -> tuple[dict[str, Any], list[str]]:
    if not path.exists():
        return {}, ["同步文件不存在"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, [f"同步文件无法读取：{exc}"]
    if not isinstance(data, dict):
        return {}, ["同步文件根节点必须是 JSON 对象"]
    errors = [f"缺少字段：{key}" for key in sorted(REQUIRED_KEYS - data.keys())]
    for table in SYNC_TABLES:
        data.setdefault(table, [])
        if not isinstance(data[table], list):
            errors.append(f"{table} 必须是数组")
            data[table] = []
    return data, errors


def export_sync_snapshot(db_path: Path = DATABASE_PATH, sync_path: Path = SYNC_FILE) -> dict[str, Any]:
    ensure_directories()
    init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        payload = {
            "schema_version": 1,
            "exported_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "exported_from_os": platform.system(),
            "exported_from_hostname": socket.gethostname(),
            "app_version": APP_VERSION,
            **{table: _rows(conn, table) for table in SYNC_TABLES},
        }
    settings = {row.get("key"): row.get("value") for row in payload["app_settings"]}
    payload["asset_allocation_targets"] = settings.get("target_allocations")
    payload["review_stats_config"] = settings.get("review_stats_config")
    payload["daily_report_config"] = settings.get("daily_report_config")
    sync_path.parent.mkdir(parents=True, exist_ok=True)
    sync_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    return {"exported_at": payload["exported_at"], "counts": {t: len(payload[t]) for t in SYNC_TABLES}, "file_path": str(sync_path)}


def backup_database(reason: str = "manual", db_path: Path = DATABASE_PATH, backup_dir: Path = BACKUPS_DIR) -> Path:
    ensure_directories()
    if not db_path.exists():
        init_db(db_path)
    safe_reason = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in reason)[:40] or "backup"
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / f"investment_dashboard_{datetime.now():%Y%m%d_%H%M%S_%f}_{safe_reason}.db"
    shutil.copy2(db_path, target)
    return target


def import_sync_snapshot(mode: str = "preview", db_path: Path = DATABASE_PATH, sync_path: Path = SYNC_FILE) -> dict[str, Any]:
    if mode not in {"preview", "merge", "overwrite"}:
        raise ValueError("mode 必须是 preview、merge 或 overwrite")
    data, validation_errors = _load_snapshot(sync_path)
    result: dict[str, Any] = {"mode": mode, "inserted": 0, "updated": 0, "skipped": 0, "errors": validation_errors, "counts": {t: len(data.get(t, [])) for t in SYNC_TABLES}}
    if not data or validation_errors:
        return result
    if mode == "preview":
        return result
    init_db(db_path)
    result["backup_path"] = str(backup_database(f"before_{mode}", db_path))
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("BEGIN")
        if mode == "overwrite":
            for table in SYNC_TABLES:
                conn.execute(f"DELETE FROM {table}")
        for table in SYNC_TABLES:
            valid_columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            for index, raw in enumerate(data[table], 1):
                try:
                    row = {key: value for key, value in raw.items() if key in valid_columns}
                    if not row:
                        result["skipped"] += 1
                        continue
                    key_name = "key" if table == "app_settings" else "id"
                    stable = row.get(key_name)
                    exists = stable is not None and conn.execute(f"SELECT 1 FROM {table} WHERE {key_name} = ?", (stable,)).fetchone()
                    if exists:
                        if table == "holdings" and "code" in row:
                            incoming_code = str(row.get("code") or "").strip()
                            current_code = str(conn.execute("SELECT code FROM holdings WHERE id = ?", (stable,)).fetchone()[0] or "").strip()
                            if not incoming_code:
                                row.pop("code", None)
                            elif current_code and incoming_code != current_code:
                                row.pop("code", None)
                                result["errors"].append(f"holdings 第 {index} 条：代码冲突，已保留本地代码")
                        assignments = [key for key in row if key != key_name]
                        if assignments:
                            conn.execute(f"UPDATE {table} SET {', '.join(f'{key} = ?' for key in assignments)} WHERE {key_name} = ?", (*[row[k] for k in assignments], stable))
                            result["updated"] += 1
                        else:
                            result["skipped"] += 1
                    else:
                        columns = list(row)
                        conn.execute(f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})", [row[k] for k in columns])
                        result["inserted"] += 1
                except Exception as exc:
                    result["errors"].append(f"{table} 第 {index} 条：{exc}")
        conn.commit()
    except Exception as exc:
        conn.rollback()
        result["errors"].append(f"导入事务失败：{exc}")
    finally:
        conn.close()
    return result


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=BASE_DIR, capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def get_sync_status(db_path: Path = DATABASE_PATH, sync_path: Path = SYNC_FILE) -> dict[str, Any]:
    data, errors = _load_snapshot(sync_path)
    db_time = datetime.fromtimestamp(db_path.stat().st_mtime).astimezone() if db_path.exists() else None
    exported = None
    if data.get("exported_at"):
        try: exported = datetime.fromisoformat(data["exported_at"])
        except ValueError: errors.append("exported_at 格式无效")
    remote = _git("remote", "get-url", "origin") or "未配置"
    dirty = bool(_git("status", "--porcelain"))
    return {
        "device": socket.gethostname(), "os": platform.system(), "database_path": str(db_path),
        "sync_path": str(sync_path), "sync_exists": sync_path.exists(), "sync_exported_at": data.get("exported_at"),
        "sync_source": data.get("exported_from_hostname"), "local_updated_at": db_time.isoformat(timespec="seconds") if db_time else None,
        "possibly_out_of_sync": bool(db_time and exported and db_time > exported), "git_branch": _git("branch", "--show-current") or "未知",
        "git_remote": remote, "git_dirty": dirty, "errors": errors,
    }
