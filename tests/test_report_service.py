from pathlib import Path

from src.report_service import generate_daily_report, localize_records, save_daily_report


def test_empty_report_and_markdown(tmp_path: Path) -> None:
    report = generate_daily_report([], [], [])
    assert report["overview"]["total_asset"] == 0
    assert "总资产" in report["markdown"] and "风险提示" in report["markdown"] and "复盘提醒" in report["markdown"]
    assert save_daily_report(report, tmp_path).exists()


def test_report_core_metrics() -> None:
    holdings = [{"name":"现金", "platform":"手动", "asset_type":"现金", "current_value":100, "cost_amount":100,
                 "target_min_ratio":.1, "target_max_ratio":.3, "risk_level":"低"}]
    report = generate_daily_report(holdings, [], [])
    assert report["overview"]["total_asset"] == 100


def test_user_facing_report_columns_are_chinese() -> None:
    rows = localize_records([{"id": 1, "name": "A500", "current_value": 12345.67, "profit_rate": .0123, "updated_at": "x"}])
    assert rows == [{"名称": "A500", "当前市值": "¥12,345.67", "收益率": "+1.23%"}]
    report = generate_daily_report([{"name":"A500", "platform":"东方财富", "asset_type":"A股宽基", "current_value":100, "cost_amount":90, "risk_level":"中"}], [], [])
    assert "| 名称 | 浮盈亏 | 收益率 |" in report["markdown"] and "profit_amount" not in report["markdown"]


def test_report_contains_market_snapshot_and_screenshot_notice() -> None:
    holdings = [{"id":1,"name":"脱敏持仓","platform":"手动","asset_type":"其他","current_value":100,"cost_amount":100,"risk_level":"中"}]
    snapshots = [{"holding_id":1,"name":"脱敏持仓","source":"screenshot","daily_pnl":-2,"change_pct":-.02}]
    report = generate_daily_report(holdings, [], [], snapshots=snapshots)
    assert report["market_snapshot"]["daily_pnl"] == -2
    assert "今日市场快照" in report["markdown"]
    assert "第三方 App 截图，仅供复盘参考" in report["markdown"]


def test_report_without_market_snapshot_is_safe() -> None:
    report = generate_daily_report([], [], [], snapshots=[])
    assert report["market_snapshot"]["count"] == 0 and "暂无今日收益快照" in report["markdown"]
    market = report.get("market_snapshot", {})
    assert {"available","source","source_label","total_daily_pnl","matched_count","missing_count","updated_at","top_gainers","top_losers","top_daily_losses","message"} <= market.keys()
