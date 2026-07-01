from src.database import fetch_all, init_db, insert_row
from src.import_service import dedupe_import_holdings, import_holding_drafts, normalize_holding_key


def holding(name="华安基金", platform="支付宝", code="", value=100):
    return {"name":name, "platform":platform, "code":code, "asset_type":"其他", "market":"A股", "current_value":value,
            "cost_amount":90, "profit_amount":value-90, "risk_level":"中", "duplicate_action":"覆盖更新"}


def test_batch_duplicate_keeps_last_result():
    rows, count = dedupe_import_holdings([holding(value=100), holding(name=" 华安基金 定投", value=120)])
    assert count == 1 and rows[0]["current_value"] == 120


def test_same_name_or_code_updates_only_same_platform(tmp_path):
    db = tmp_path / "test.db"; init_db(db)
    assert import_holding_drafts([holding(value=100)], db)["inserted"] == 1
    assert import_holding_drafts([holding(name="华安 基金", value=130)], db)["updated"] == 1
    assert import_holding_drafts([holding(name="别名", code="000001", value=200)], db)["inserted"] == 1
    assert import_holding_drafts([holding(name="新名称", code="000001", value=220)], db)["updated"] == 1
    assert import_holding_drafts([holding(platform="东方财富", value=300)], db)["inserted"] == 1
    assert len(fetch_all("holdings", db)) == 3


def test_overwrite_preserves_trades_and_plans(tmp_path):
    db = tmp_path / "test.db"; init_db(db); import_holding_drafts([holding()], db)
    insert_row("trades", {"trade_date":"2026-07-01", "asset_name":"华安基金", "action":"买入"}, db)
    insert_row("plans", {"asset_name":"华安基金", "plan_type":"补仓"}, db)
    import_holding_drafts([holding(value=150)], db)
    assert len(fetch_all("trades", db)) == 1 and len(fetch_all("plans", db)) == 1
    assert fetch_all("holdings", db)[0]["current_value"] == 150


def test_normalized_key_uses_platform_and_code():
    assert normalize_holding_key(holding(name="A（QDII） 定投")) == normalize_holding_key(holding(name="a(QDII)"))
    assert normalize_holding_key(holding(code=" 000001 ")) != normalize_holding_key(holding(code="000002"))
