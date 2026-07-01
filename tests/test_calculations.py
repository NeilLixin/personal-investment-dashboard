import pytest

from src.calculations import apply_holding_operation, allocation_status, calculate_asset_ratio, calculate_profit, portfolio_summary


def test_profit_and_rate_are_calculated() -> None:
    profit, rate = calculate_profit(12_000, 10_000)
    assert profit == 2_000
    assert rate == pytest.approx(0.2)


def test_zero_cost_and_zero_total_are_safe() -> None:
    assert calculate_profit(1_000, 0)[1] == 0
    assert calculate_asset_ratio(1_000, 0) == 0


def test_asset_ratio_and_target_status() -> None:
    assert calculate_asset_ratio(25, 100) == pytest.approx(0.25)
    assert allocation_status(0.05, 0.10, 0.20) == "低配"
    assert allocation_status(0.15, 0.10, 0.20) == "正常"
    assert allocation_status(0.25, 0.10, 0.20) == "超配"


def test_portfolio_summary() -> None:
    rows = [
        {"name": "现金", "asset_type": "现金", "current_value": 20, "cost_amount": 20, "target_min_ratio": 0, "target_max_ratio": 1, "risk_level": "低"},
        {"name": "A500", "asset_type": "A股宽基", "current_value": 80, "cost_amount": 70, "target_min_ratio": 0, "target_max_ratio": 1, "risk_level": "中"},
    ]
    summary = portfolio_summary(rows)
    assert summary["total_asset"] == 100
    assert summary["total_profit"] == 10
    assert summary["cash_ratio"] == pytest.approx(0.2)


def test_quick_buy_and_sell_update_holding_safely() -> None:
    source = {"current_value":1000, "cost_amount":800, "holding_share":100, "latest_price":10}
    bought = apply_holding_operation(source, "补仓", 200, 20, 11)
    assert bought["current_value"] == 1200 and bought["cost_amount"] == 1000 and bought["holding_share"] == 120 and bought["latest_price"] == 11
    sold = apply_holding_operation(source, "减仓", 250, 30)
    assert sold["current_value"] == 750 and sold["cost_amount"] == 600 and sold["holding_share"] == 70
    cleared = apply_holding_operation(source, "卖出", 5000, 500)
    assert cleared["current_value"] == 0 and cleared["cost_amount"] == 0 and cleared["holding_share"] is None


def test_observe_does_not_change_holding():
    source = {"current_value":1000, "cost_amount":800, "holding_share":100}
    observed = apply_holding_operation(source, "观察", 999, 99)
    assert observed["current_value"] == 1000 and observed["cost_amount"] == 800 and observed["holding_share"] == 100
