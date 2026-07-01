from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Mapping

import pandas as pd

from src.calculations import calculate_profit, safe_float
from src.config import DATABASE_PATH
from src.database import connection, insert_row, update_row

IMPORT_COLUMNS = ["name", "code", "platform", "asset_type", "market", "current_value", "cost_amount", "profit_amount",
                  "profit_rate", "yesterday_profit", "holding_share", "latest_price", "target_min_ratio", "target_max_ratio",
                  "risk_level", "note", "duplicate_action"]
HOLDING_FIELDS = set(IMPORT_COLUMNS) - {"duplicate_action", "yesterday_profit"}


def normalize_holding_key(holding: Mapping) -> str:
    """Build a platform-scoped key, preferring security code over normalized display name."""
    platform = re.sub(r"\s+", "", str(holding.get("platform") or "其他")).upper()
    code = re.sub(r"\s+", "", str(holding.get("code") or "")).upper()
    if code:
        return f"{platform}|CODE:{code}"
    name = str(holding.get("name") or "").replace("（", "(").replace("）", ")")
    name = re.sub(r"\s+", "", name, flags=re.MULTILINE)
    name = re.sub(r"(?:定投)+$", "", name, flags=re.IGNORECASE).upper()
    return f"{platform}|NAME:{name}"


def dedupe_import_holdings(holdings: Iterable[Mapping]) -> tuple[list[dict], int]:
    unique: dict[str, dict] = {}; duplicate_count = 0
    for holding in holdings:
        key = normalize_holding_key(holding)
        if key in unique: duplicate_count += 1
        unique[key] = dict(holding)
    return list(unique.values()), duplicate_count


def match_existing_holding(holding: Mapping, db_path: Path = DATABASE_PATH) -> dict | None:
    platform, code = str(holding.get("platform") or "其他"), str(holding.get("code") or "").strip()
    with connection(db_path) as conn:
        if code:
            row = conn.execute("SELECT * FROM holdings WHERE platform = ? AND UPPER(TRIM(code)) = UPPER(?) ORDER BY id LIMIT 1", (platform, code)).fetchone()
            return dict(row) if row else None
        candidates = conn.execute("SELECT * FROM holdings WHERE platform = ? ORDER BY id", (platform,)).fetchall()
    key = normalize_holding_key(holding)
    return next((dict(row) for row in candidates if normalize_holding_key(dict(row)) == key), None)


def apply_import_strategy(holding: Mapping, strategy: str = "覆盖更新", db_path: Path = DATABASE_PATH) -> str:
    source = dict(holding); existing = match_existing_holding(source, db_path)
    if strategy == "跳过": return "skipped"
    item = {key: value for key, value in source.items() if key in HOLDING_FIELDS}
    item["daily_profit"] = source.get("yesterday_profit", source.get("today_profit"))
    current, cost = safe_float(item.get("current_value")), safe_float(item.get("cost_amount"))
    profit, rate = calculate_profit(current, cost, item.get("profit_amount"))
    item.update({"current_value": current, "cost_amount": cost, "profit_amount": profit, "profit_rate": rate})
    if existing and strategy == "覆盖更新":
        update_row("holdings", existing["id"], item, db_path); return "updated"
    insert_row("holdings", item, db_path); return "inserted"


def parsed_to_drafts(parsed: Iterable[Mapping]) -> pd.DataFrame:
    rows = []
    for item in parsed:
        current = safe_float(item.get("current_value")); cost = safe_float(item.get("cost_amount"), current-safe_float(item.get("profit_amount")))
        profit, rate = calculate_profit(current, cost, item.get("profit_amount")); parsed_rate = safe_float(item.get("profit_rate"), rate)
        if abs(parsed_rate) > 1: parsed_rate /= 100
        rows.append({"name":item.get("name", ""), "code":item.get("code") or "", "platform":item.get("platform", "支付宝"),
            "asset_type":item.get("asset_type", "其他"), "market":item.get("market", "其他"), "current_value":current,
            "cost_amount":cost, "profit_amount":profit, "profit_rate":parsed_rate,
            "yesterday_profit":item.get("yesterday_profit", item.get("today_profit")), "holding_share":item.get("holding_share"),
            "latest_price":item.get("latest_price"), "target_min_ratio":safe_float(item.get("target_min_ratio")),
            "target_max_ratio":safe_float(item.get("target_max_ratio"), 1), "risk_level":item.get("risk_level", "中"),
            "note":item.get("note", "截图导入"), "duplicate_action":"覆盖更新"})
    return pd.DataFrame(rows, columns=IMPORT_COLUMNS)


def import_holding_drafts(records: Iterable[Mapping], db_path: Path = DATABASE_PATH) -> dict[str, int]:
    rows, duplicates = dedupe_import_holdings(records)
    result = {"inserted":0, "updated":0, "skipped":0, "failed":0, "duplicates":duplicates}
    for source in rows:
        try:
            outcome = apply_import_strategy(source, source.get("duplicate_action", "覆盖更新"), db_path); result[outcome] += 1
        except Exception:
            result["failed"] += 1
    return result
