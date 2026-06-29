from src.rule_engine import evaluate_risks


def test_low_cash_and_concentration_rules() -> None:
    holdings = [
        {"name": "半导体", "asset_type": "A股科技/半导体/通信", "current_value": 95, "cost_amount": 90, "target_min_ratio": 0.05, "target_max_ratio": 0.30, "risk_level": "高"},
        {"name": "现金", "asset_type": "现金", "current_value": 5, "cost_amount": 5, "target_min_ratio": 0.10, "target_max_ratio": 0.25, "risk_level": "低"},
    ]
    risks = evaluate_risks(holdings)
    titles = {item["title"] for item in risks}
    assert "现金比例过低" in titles
    assert "单一资产占比过高" in titles
    assert "科技仓位超过目标" in titles


def test_normal_portfolio_returns_normal_signal() -> None:
    holdings = [
        {"name": "现金", "asset_type": "现金", "current_value": 20, "cost_amount": 20, "target_min_ratio": 0.1, "target_max_ratio": 0.3, "risk_level": "低"},
        {"name": "宽基", "asset_type": "A股宽基", "current_value": 25, "cost_amount": 24, "target_min_ratio": 0.1, "target_max_ratio": 0.4, "risk_level": "中"},
        {"name": "债券", "asset_type": "债券/固收", "current_value": 25, "cost_amount": 25, "target_min_ratio": 0.1, "target_max_ratio": 0.4, "risk_level": "低"},
        {"name": "海外", "asset_type": "海外资产", "current_value": 15, "cost_amount": 14, "target_min_ratio": 0.1, "target_max_ratio": 0.3, "risk_level": "中"},
        {"name": "黄金", "asset_type": "黄金", "current_value": 15, "cost_amount": 14, "target_min_ratio": 0.05, "target_max_ratio": 0.2, "risk_level": "中"},
    ]
    risks = evaluate_risks(holdings)
    assert any(item["level"] == "normal" for item in risks)
