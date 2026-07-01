import json
import sqlite3
from pathlib import Path

from src.database import init_db, insert_row
from src.sync_service import export_sync_snapshot, get_sync_status, import_sync_snapshot


def test_export_and_preview_do_not_change_database(tmp_path: Path) -> None:
    db, sync = tmp_path / "local.db", tmp_path / "portfolio_sync.json"
    init_db(db)
    insert_row("holdings", {"name":"现金", "platform":"手动", "asset_type":"现金", "market":"现金"}, db)
    result = export_sync_snapshot(db, sync)
    payload = json.loads(sync.read_text(encoding="utf-8"))
    assert result["counts"]["holdings"] == 1
    assert "uploads" not in payload and "image" not in payload
    before = db.read_bytes()
    preview = import_sync_snapshot("preview", db, sync)
    assert preview["counts"]["holdings"] == 1 and db.read_bytes() == before


def test_overwrite_creates_backup(tmp_path: Path) -> None:
    db, sync = tmp_path / "local.db", tmp_path / "portfolio_sync.json"
    init_db(db); export_sync_snapshot(db, sync)
    result = import_sync_snapshot("overwrite", db, sync)
    assert Path(result["backup_path"]).exists()


def test_missing_fields_is_graceful(tmp_path: Path) -> None:
    sync = tmp_path / "bad.json"; sync.write_text("{}", encoding="utf-8")
    result = import_sync_snapshot("preview", tmp_path / "local.db", sync)
    assert result["errors"]


def test_sync_status_keeps_ui_and_advanced_information_separate(tmp_path: Path) -> None:
    status = get_sync_status(tmp_path / "local.db", tmp_path / "sync.json")
    assert "database_path" in status and "sync_path" in status
    assert status["sync_exists"] is False
