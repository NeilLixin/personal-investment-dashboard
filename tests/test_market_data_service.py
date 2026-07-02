from datetime import datetime, timedelta, timezone

import src.market_data_service as service
from src.database import fetch_all, init_db, insert_row


def sample_holding(row_id=1, code="510001", name="示例ETF"):
    return {"id":row_id, "name":name, "code":code, "platform":"手动", "asset_type":"A股宽基", "market":"A股",
            "current_value":1000, "holding_share":100}


def test_refresh_interval_and_force(tmp_path):
    db = tmp_path / "market.db"; init_db(db); now = datetime.now(timezone.utc)
    assert service.should_refresh_market_snapshots(now, 60, db_path=db)
    service.save_market_snapshot({"holding_id":1,"source":"market_api","snapshot_date":now.date().isoformat(),"fetched_at":now.isoformat()}, db)
    assert not service.should_refresh_market_snapshots(now + timedelta(minutes=30), 60, db_path=db)
    assert service.should_refresh_market_snapshots(now + timedelta(minutes=61), 60, db_path=db)
    assert service.should_refresh_market_snapshots(now, 60, force=True, db_path=db)


def test_daily_pnl_prefers_shares_then_estimate():
    exact = service.calculate_daily_pnl({"holding_share":100}, {"price":2.1,"previous_price":2.0,"change_pct":.05})
    assert exact["daily_pnl"] == 10 and exact["daily_pnl_estimated"] == 0
    estimated = service.calculate_daily_pnl({"current_value":1050}, {"change_pct":.05})
    assert estimated["daily_pnl"] == 50 and estimated["daily_pnl_estimated"] == 1


def test_save_upserts_and_latest(tmp_path):
    db = tmp_path / "market.db"; init_db(db)
    base = {"holding_id":1,"source":"screenshot","snapshot_date":"2026-07-02","fetched_at":"2026-07-02T10:00:00","daily_pnl":10}
    service.save_market_snapshot(base, db); service.save_market_snapshot({**base,"daily_pnl":20}, db)
    assert len(fetch_all("market_snapshots", db)) == 1
    assert service.get_latest_market_snapshots(db)[0]["daily_pnl"] == 20


def test_single_failure_does_not_stop_refresh(monkeypatch, tmp_path):
    db = tmp_path / "market.db"; init_db(db)
    def fake_fetch(holding):
        if holding["id"] == 1: return {"ok":False,"status":"failed","error":"模拟失败","source_name":"akshare"}
        return {"ok":True,"status":"success","quality_level":"realtime_quote","source_name":"akshare","price":2,"previous_price":1.9,"change_pct":.05}
    monkeypatch.setattr(service, "fetch_quote_for_holding", fake_fetch)
    result = service.refresh_market_snapshots_for_holdings([sample_holding(1), sample_holding(2,"510002")], True, db)
    assert result["failed"] == 1 and result["success"] == 1
    assert len(fetch_all("market_refresh_logs", db)) == 1


def test_missing_code_is_skipped_and_missing_akshare_is_safe(monkeypatch):
    assert service.fetch_quote_for_holding(sample_holding(code=""))["status"] == "skipped"
    # The optional dependency may or may not exist in the test environment; either outcome is structured.
    result = service.fetch_quote_for_holding(sample_holding())
    assert isinstance(result, dict) and "status" in result


def test_instrument_inference_uses_six_digit_code_without_asset_type():
    assert service.infer_market_instrument_type({"code":"006075","asset_type":""})["instrument_type"] == "open_fund"
    assert service.infer_market_instrument_type({"fund_code":"159995","asset_type":""})["instrument_type"] == "exchange_etf"
    assert service.infer_market_instrument_type({"symbol":6075})["instrument_type"] == "open_fund"


def test_provider_unavailable_and_network_failure_are_not_skipped(monkeypatch):
    def unavailable(): raise service.ProviderUnavailable("市场数据依赖未安装，可执行 pip install akshare")
    monkeypatch.setattr(service, "_load_akshare", unavailable)
    missing = service.fetch_quote_for_holding({"code":"006075","asset_type":""})
    assert missing["status"] == "provider_unavailable" and missing["status"] != "skipped"
    class BrokenAK:
        def fund_open_fund_daily_em(self): raise ConnectionError("offline")
        def fund_etf_spot_em(self): raise ConnectionError("offline")
    failed = service.fetch_quote_for_holding({"code":"006075"}, BrokenAK())
    assert failed["status"] == "failed"


def test_only_unsupported_holdings_are_skipped():
    assert service.fetch_quote_for_holding({"name":"无代码资产","code":""})["status"] == "skipped"
    assert service.fetch_quote_for_holding({"name":"现金","asset_type":"现金"})["status"] == "skipped"


def test_refresh_result_shape_and_skip_reasons(tmp_path):
    db = tmp_path / "market.db"; init_db(db)
    result = service.refresh_market_snapshots_for_holdings([{"id":1,"name":"无代码资产","code":""}], True, db)
    required = {"total","success_count","failed_count","skipped_count","success_items","failed_items","skipped_items","message"}
    assert required <= result.keys()
    assert result["skipped_count"] == 1 and result["skipped_items"][0]["reason"]
