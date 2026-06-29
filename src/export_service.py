from __future__ import annotations

import shutil
import zipfile
from datetime import datetime
from pathlib import Path

import pandas as pd

from src.config import BACKUPS_DIR, DATABASE_PATH, EXPORTS_DIR, ensure_directories
from src.database import fetch_all


EXPORT_TABLES = ("holdings", "trades", "plans", "rules")


def export_table_csv(table: str, destination: Path | None = None) -> Path:
    ensure_directories()
    destination = destination or EXPORTS_DIR / f"{table}_{datetime.now():%Y%m%d_%H%M%S}.csv"
    pd.DataFrame(fetch_all(table)).to_csv(destination, index=False, encoding="utf-8-sig")
    return destination


def export_all_csv_zip() -> Path:
    ensure_directories()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive = EXPORTS_DIR / f"investment_csv_{stamp}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for table in EXPORT_TABLES:
            path = export_table_csv(table, EXPORTS_DIR / f"{table}_{stamp}.csv")
            bundle.write(path, path.name)
    return archive


def backup_database() -> Path:
    ensure_directories()
    if not DATABASE_PATH.exists():
        raise FileNotFoundError("数据库尚未创建")
    target = BACKUPS_DIR / f"investment_dashboard_{datetime.now():%Y%m%d_%H%M%S}.db"
    shutil.copy2(DATABASE_PATH, target)
    return target
