import pytest

from src.calculations import allocation_status, calculate_asset_ratio, calculate_profit, portfolio_summary


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
