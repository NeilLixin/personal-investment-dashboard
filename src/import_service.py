from __future__ import annotations

from typing import Iterable, Mapping

import pandas as pd

from src.calculations import calculate_profit, safe_float
from src.database import find_holding, insert_row, update_row


IMPORT_COLUMNS = [
    "name", "code", "platform", "asset_type", "market", "current_value", "cost_amount",
    "profit_amount", "profit_rate", "yesterday_profit", "holding_share", "latest_price", "target_min_ratio",
    "target_max_ratio", "risk_level", "note", "duplicate_action",
]
HOLDING_FIELDS = set(IMPORT_COLUMNS) - {"duplicate_action", "yesterday_profit"}


def parsed_to_drafts(parsed: Iterable[Mapping]) -> pd.DataFrame:
    rows = []
    for item in parsed:
        current = safe_float(item.get("current_value"))
        cost = safe_float(item.get("cost_amount"), current - safe_float(item.get("profit_amount")))
        profit, rate = calculate_profit(current, cost, item.get("profit_amount"))
        parsed_rate = safe_float(item.get("profit_rate"), rate)
        # The dedicated parser returns the displayed percentage (21.01);
        # holdings stores the equivalent decimal ratio (0.2101).
        if abs(parsed_rate) > 1:
            parsed_rate /= 100
        rows.append({
            "name": item.get("name", ""), "code": item.get("code") or "", "platform": item.get("platform", "支付宝"),
            "asset_type": item.get("asset_type", "其他"), "market": item.get("market", "其他"),
            "current_value": current, "cost_amount": cost, "profit_amount": profit,
            "profit_rate": parsed_rate, "yesterday_profit": item.get("yesterday_profit", item.get("today_profit")),
            "holding_share": item.get("holding_share"),
            "latest_price": item.get("latest_price"), "target_min_ratio": safe_float(item.get("target_min_ratio")),
            "target_max_ratio": safe_float(item.get("target_max_ratio"), 1.0), "risk_level": item.get("risk_level", "中"),
            "note": item.get("note", "截图导入"), "duplicate_action": "覆盖更新",
        })
    return pd.DataFrame(rows, columns=IMPORT_COLUMNS)


def import_holding_drafts(records: Iterable[Mapping]) -> dict[str, int]:
    result = {"inserted": 0, "updated": 0, "skipped": 0}
    for raw in records:
        source = dict(raw)
        action = source.get("duplicate_action", "覆盖更新")
        item = {key: value for key, value in source.items() if key in HOLDING_FIELDS}
        current = safe_float(item.get("current_value"))
        cost = safe_float(item.get("cost_amount"))
        profit, rate = calculate_profit(current, cost, item.get("profit_amount"))
        item.update({"current_value": current, "cost_amount": cost, "profit_amount": profit, "profit_rate": rate})
        existing = find_holding(str(item.get("name", "")), str(item.get("code", "")))
        if existing and action == "跳过":
            result["skipped"] += 1
            continue
        if existing and action == "覆盖更新":
            update_row("holdings", existing["id"], item)
            result["updated"] += 1
        else:
            insert_row("holdings", item)
            result["inserted"] += 1
    return result
