from __future__ import annotations

from typing import Iterable, Mapping

import pandas as pd


def safe_float(value, default: float = 0.0) -> float:
    try:
        if value is None or pd.isna(value) or value == "":
            return default
        return float(str(value).replace(",", "").replace("¥", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return default


def calculate_profit(current_value: float, cost_amount: float, profit_amount=None) -> tuple[float, float]:
    current = safe_float(current_value)
    cost = safe_float(cost_amount)
    profit = safe_float(profit_amount, current - cost) if profit_amount not in (None, "") else current - cost
    rate = profit / cost if cost else 0.0
    return round(profit, 2), round(rate, 6)


def calculate_asset_ratio(current_value: float, total_asset: float) -> float:
    total = safe_float(total_asset)
    return round(safe_float(current_value) / total, 6) if total else 0.0


def allocation_status(current_ratio: float, target_min_ratio: float, target_max_ratio: float) -> str:
    ratio = safe_float(current_ratio)
    minimum = safe_float(target_min_ratio)
    maximum = safe_float(target_max_ratio, 1.0)
    if ratio < minimum:
        return "低配"
    if ratio > maximum:
        return "超配"
    return "正常"


def enrich_holdings(records: Iterable[Mapping]) -> pd.DataFrame:
    frame = pd.DataFrame(list(records))
    if frame.empty:
        return frame
    for column in ("current_value", "cost_amount", "profit_rate", "target_min_ratio", "target_max_ratio"):
        if column not in frame:
            frame[column] = 0.0
        frame[column] = frame[column].apply(safe_float)
    if "profit_amount" not in frame:
        frame["profit_amount"] = None
    frame["profit_amount"] = frame.apply(
        lambda row: calculate_profit(row["current_value"], row["cost_amount"], row.get("profit_amount"))[0], axis=1
    )
    frame["profit_rate"] = frame.apply(
        lambda row: calculate_profit(row["current_value"], row["cost_amount"], row["profit_amount"])[1], axis=1
    )
    total = frame["current_value"].sum()
    frame["asset_ratio"] = frame["current_value"].apply(lambda value: calculate_asset_ratio(value, total))
    frame["allocation_status"] = frame.apply(
        lambda row: allocation_status(row["asset_ratio"], row["target_min_ratio"], row["target_max_ratio"]), axis=1
    )
    frame["display_status"] = frame.apply(
        lambda row: "🔴 高风险" if row.get("risk_level") == "高" else (
            "🟡 " + row["allocation_status"] if row["allocation_status"] != "正常" else "🟢 正常"
        ), axis=1
    )
    return frame


def portfolio_summary(records: Iterable[Mapping]) -> dict[str, float]:
    frame = enrich_holdings(records)
    if frame.empty:
        return {"total_asset": 0.0, "total_cost": 0.0, "total_profit": 0.0, "profit_rate": 0.0, "cash_ratio": 0.0}
    total_asset = float(frame["current_value"].sum())
    total_cost = float(frame["cost_amount"].sum())
    total_profit = float(frame["profit_amount"].sum())
    cash_value = float(frame.loc[frame["asset_type"] == "现金", "current_value"].sum())
    return {
        "total_asset": round(total_asset, 2),
        "total_cost": round(total_cost, 2),
        "total_profit": round(total_profit, 2),
        "profit_rate": round(total_profit / total_cost, 6) if total_cost else 0.0,
        "cash_ratio": round(cash_value / total_asset, 6) if total_asset else 0.0,
    }


def format_currency(value: float, signed: bool = False) -> str:
    number = safe_float(value)
    prefix = "+" if signed and number > 0 else ""
    return f"{prefix}¥{number:,.2f}"


def format_rate(value: float, signed: bool = False) -> str:
    number = safe_float(value) * 100
    prefix = "+" if signed and number > 0 else ""
    return f"{prefix}{number:.2f}%"
