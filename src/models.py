from dataclasses import dataclass
from typing import Optional


@dataclass
class Holding:
    name: str
    platform: str
    asset_type: str
    market: str
    current_value: float
    cost_amount: float
    code: str = ""
    profit_amount: Optional[float] = None
    profit_rate: Optional[float] = None
    holding_share: Optional[float] = None
    latest_price: Optional[float] = None
    target_min_ratio: float = 0.0
    target_max_ratio: float = 1.0
    risk_level: str = "中"
    note: str = ""


@dataclass
class Trade:
    trade_date: str
    asset_name: str
    action: str
    amount: float = 0.0
    price: float = 0.0
    reason: str = ""
    emotion: str = "冷静"
    plan_id: Optional[int] = None
    review_date: Optional[str] = None
    review_result: str = ""


@dataclass
class Plan:
    asset_name: str
    plan_type: str
    trigger_condition: str
    trigger_value: Optional[float]
    suggested_action: str
    priority: int = 2
    enabled: bool = True
    note: str = ""
