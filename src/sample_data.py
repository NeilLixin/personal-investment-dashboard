from datetime import date, timedelta


DEMO_HOLDINGS = [
    ("A500", "159xxx", "券商", "A股宽基", "A股", 85000, 80000, 0.15, 0.28, "中"),
    ("创业板", "159915", "支付宝", "A股科技/半导体/通信", "A股", 28000, 31000, 0.05, 0.12, "高"),
    ("半导体", "512xxx", "券商", "A股科技/半导体/通信", "A股", 36000, 34000, 0.05, 0.15, "高"),
    ("通信", "515xxx", "券商", "A股科技/半导体/通信", "A股", 18000, 16000, 0.02, 0.08, "高"),
    ("纳斯达克100", "513100", "支付宝", "海外资产", "美股", 42000, 35000, 0.10, 0.22, "高"),
    ("标普500", "513500", "支付宝", "海外资产", "美股", 26000, 24000, 0.05, 0.15, "中"),
    ("黄金", "", "支付宝", "黄金", "黄金", 52000, 45000, 0.08, 0.15, "中"),
    ("现金", "", "招商银行", "现金", "现金", 38000, 38000, 0.10, 0.25, "低"),
    ("债券/固收", "", "浙商银行", "债券/固收", "其他", 45000, 44000, 0.10, 0.22, "低"),
]

DEMO_PLANS = [
    ("A500", "补仓", "回调幅度达到", 2, "接回卖出仓位的 30%", 1),
    ("黄金", "减仓", "接近成本价或反弹", 0, "减仓 20%", 2),
    ("现金", "观察", "现金比例低于", 10, "停止主动加仓", 1),
    ("科技类", "减仓", "科技仓位超过", 30, "禁止继续追涨", 1),
]

DEMO_TRADES = [
    ((date.today() - timedelta(days=5)).isoformat(), "A500", "定投", 3000, 0, "执行月度计划", "按计划", (date.today() + timedelta(days=2)).isoformat()),
    ((date.today() - timedelta(days=12)).isoformat(), "黄金", "减仓", 5000, 0, "仓位接近上限", "冷静", date.today().isoformat()),
    ((date.today() - timedelta(days=20)).isoformat(), "半导体", "补仓", 2000, 0, "担心踏空", "怕踏空", (date.today() - timedelta(days=2)).isoformat()),
]

DEFAULT_ALLOCATION = {
    "现金": {"min": 0.10, "max": 0.25}, "A股宽基": {"min": 0.15, "max": 0.30},
    "A股科技/半导体/通信": {"min": 0.08, "max": 0.25}, "海外资产": {"min": 0.10, "max": 0.25},
    "黄金": {"min": 0.08, "max": 0.15}, "债券/固收": {"min": 0.10, "max": 0.25},
    "其他": {"min": 0.00, "max": 0.10},
}


def seed_demo_data(skip_if_holdings_exist: bool = True) -> bool:
    """Insert privacy-safe sample data. Returns False when existing holdings are preserved."""
    from src.calculations import calculate_profit
    from src.database import fetch_all, insert_row, set_setting

    if skip_if_holdings_exist and fetch_all("holdings"):
        return False
    for name, code, platform, asset_type, market, current, cost, minimum, maximum, risk in DEMO_HOLDINGS:
        profit, rate = calculate_profit(current, cost)
        insert_row("holdings", {
            "name": name, "code": code, "platform": platform, "asset_type": asset_type, "market": market,
            "current_value": current, "cost_amount": cost, "profit_amount": profit, "profit_rate": rate,
            "target_min_ratio": minimum, "target_max_ratio": maximum, "risk_level": risk, "note": "模拟数据",
        })
    for asset, kind, condition, value, action, priority in DEMO_PLANS:
        insert_row("plans", {"asset_name": asset, "plan_type": kind, "trigger_condition": condition,
                              "trigger_value": value, "suggested_action": action, "priority": priority,
                              "enabled": 1, "note": "模拟计划"})
    for trade_date, asset, action, amount, price, reason, emotion, review_date in DEMO_TRADES:
        insert_row("trades", {"trade_date": trade_date, "asset_name": asset, "action": action,
                               "amount": amount, "price": price, "reason": reason, "emotion": emotion,
                               "review_date": review_date, "review_result": ""})
    set_setting("target_allocations", DEFAULT_ALLOCATION)
    return True
