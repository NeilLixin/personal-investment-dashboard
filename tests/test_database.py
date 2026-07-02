from src.database import fetch_all, init_db, insert_row


def test_market_tables_and_legacy_data_survive_init(tmp_path):
    db = tmp_path / "legacy.db"; init_db(db)
    insert_row("holdings", {"name":"脱敏持仓","platform":"手动","asset_type":"其他","market":"其他"}, db)
    insert_row("trades", {"trade_date":"2026-07-02","asset_name":"脱敏持仓","action":"观察"}, db)
    insert_row("plans", {"asset_name":"脱敏持仓","plan_type":"观察"}, db)
    init_db(db)
    assert len(fetch_all("holdings", db)) == len(fetch_all("trades", db)) == len(fetch_all("plans", db)) == 1
    assert fetch_all("market_snapshots", db) == []
    assert fetch_all("market_refresh_logs", db) == []
    assert fetch_all("screenshot_profit_import_batches", db) == []
    assert fetch_all("fund_code_candidates", db) == []
    assert fetch_all("fund_code_match_logs", db) == []
