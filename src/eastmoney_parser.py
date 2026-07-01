from __future__ import annotations

import re
from typing import Any, Iterable, Mapping


SIGN_TRANSLATION = str.maketrans({"—": "-", "－": "-", "一": "-", "＋": "+", "十": "+", "，": ",", "％": "%"})
SUMMARY_LABELS = {
    "总资产": "total_asset", "当日盈亏": "today_profit", "证券市值": "security_market_value",
    "持仓盈亏": "holding_profit", "可用": "available_cash", "可取": "withdrawable_cash",
}
IGNORE_WORDS = {"东方财富", "普通", "信用", "期权", "模拟", "期货", "买入", "卖出", "撤单", "银证转账",
                "场内基金", "市值", "持仓", "可用", "现价", "成本", "持仓盈亏", "当日盈亏", "首页", "行情", "交易", "我的"}


def parse_eastmoney_holdings_from_ocr_items(
    items: Iterable[Mapping[str, Any]] | None,
    image_width: float | None = None,
    image_height: float | None = None,
) -> dict[str, Any]:
    """Parse the Eastmoney five-column holdings table from positioned OCR blocks."""
    normalized = [_normalize_item(item) for item in (items or [])]
    normalized = sorted((item for item in normalized if item), key=lambda x: (x["center_y"], x["center_x"]))
    debug: dict[str, Any] = {"item_count": len(normalized), "name_candidates": [], "rows": [], "ignored_items": [], "warnings": []}
    if not normalized:
        return {"ok": False, "holdings": [], "account_summary": {}, "debug": debug, "error": "OCR items 为空"}
    width = float(image_width or max(item["max_x"] for item in normalized))
    height = float(image_height or max(item["max_y"] for item in normalized))
    summary = _parse_summary(normalized)

    # The holdings region begins below the five-column header. This also prevents account-summary labels
    # and top action buttons from becoming false holding names.
    header_y = max((item["center_y"] for item in normalized if "场内基金" in item["text"]), default=height * .30)
    usable = [item for item in normalized if header_y < item["center_y"] < height * .94]
    names = [item for item in usable if item["center_x"] < width * .24 and _is_name(item["text"])]
    debug["name_candidates"] = [item["text"] for item in names]
    holdings: list[dict[str, Any]] = []
    for index, name_item in enumerate(names):
        next_y = names[index + 1]["center_y"] if index + 1 < len(names) else height * .94
        start = name_item["center_y"] - max(10, name_item["height"] * .7)
        row_items = [item for item in usable if start <= item["center_y"] < next_y - 4]
        columns = [[], [], [], [], []]
        for item in row_items:
            column = min(4, int(item["center_x"] / max(width, 1) * 5))
            if _number(item["text"]) is not None:
                columns[column].append(item)
        for column in columns:
            column.sort(key=lambda x: (x["center_y"], x["center_x"]))
        values = [[_number(item["text"]) for item in column] for column in columns]
        debug["rows"].append({"name": name_item["text"], "columns": [[x["text"] for x in col] for col in columns]})
        if len(values[0]) < 1 or any(len(values[col]) < 2 for col in range(1, 5)):
            debug["warnings"].append(f"{name_item['text']} 的五列数据不完整")
            continue
        name = name_item["text"].replace(" ", "")
        asset_type, market = infer_eastmoney_classification(name)
        current_value, holding_share, latest_price, profit_amount, today_profit = (values[i][0] for i in range(5))
        available_share, cost_price, profit_rate, today_profit_rate = values[1][1], values[2][1], values[3][1], values[4][1]
        holdings.append({
            "name": name, "code": "", "platform": "东方财富", "asset_type": asset_type, "market": market,
            "current_value": current_value, "cost_amount": round(current_value - profit_amount, 2),
            "profit_amount": profit_amount, "profit_rate": profit_rate, "today_profit": today_profit,
            "holding_share": holding_share, "available_share": available_share, "latest_price": latest_price,
            "cost_price": cost_price, "today_profit_rate": today_profit_rate, "risk_level": "中",
            "note": "东方财富持仓截图导入",
        })
    if not holdings:
        return {"ok": False, "holdings": [], "account_summary": summary, "debug": debug,
                "error": "已识别到文字，但没有匹配到完整的东方财富五列持仓"}
    return {"ok": True, "holdings": holdings, "account_summary": summary, "debug": debug, "error": ""}


def infer_eastmoney_classification(name: str) -> tuple[str, str]:
    upper = name.upper()
    if any(key in upper for key in ("A500", "沪深300", "中证500", "创业板", "上证", "宽基")):
        return "A股宽基", "A股"
    if any(key in upper for key in ("芯片", "半导体", "通信", "科技", "人工智能", "AI", "算力", "光伏", "新能源", "电网")):
        return "A股科技/半导体/通信", "A股"
    if any(key in upper for key in ("纳斯达克", "标普", "QDII", "全球", "美股")):
        return "海外资产", "海外"
    if "黄金" in upper:
        return "黄金", "黄金"
    if any(key in upper for key in ("债", "货币", "现金", "短债")):
        return "债券/固收", "其他"
    return "其他", "A股"


def _parse_summary(items: list[dict[str, Any]]) -> dict[str, float]:
    result: dict[str, float] = {}
    for label, key in SUMMARY_LABELS.items():
        candidates = [item for item in items if item["text"].strip() == label]
        for candidate in candidates:
            nearby = [item for item in items if item["center_y"] >= candidate["center_y"] and
                      item["center_y"] - candidate["center_y"] < candidate["height"] * 3.5 and
                      abs(item["center_x"] - candidate["center_x"]) < max(candidate["width"] * 2, 180) and
                      _number(item["text"]) is not None]
            if nearby:
                result[key] = _number(min(nearby, key=lambda x: (x["center_y"], abs(x["center_x"] - candidate["center_x"]))) ["text"])
                break
    return result


def _is_name(text: str) -> bool:
    compact = text.strip()
    return compact not in IGNORE_WORDS and not re.fullmatch(r"[+十\-—－一]?\d[\d,.]*%?", compact) and len(compact) >= 2


def _number(value: str) -> float | None:
    text = value.translate(SIGN_TRANSLATION).replace(" ", "").replace("¥", "").replace("￥", "")
    if not re.fullmatch(r"[+\-]?\d[\d,]*(?:\.\d+)?%?", text):
        return None
    try:
        return float(text.replace(",", "").replace("%", ""))
    except ValueError:
        return None


def _normalize_item(raw: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(raw, Mapping):
        return None
    text = re.sub(r"\s+", " ", str(raw.get("text") or raw.get("txt") or "")).strip()
    try:
        box = raw.get("box") or []
        if raw.get("center_x") is not None:
            cx, cy = float(raw["center_x"]), float(raw["center_y"])
            min_x, max_x = float(raw.get("min_x", cx)), float(raw.get("max_x", cx))
            min_y, max_y = float(raw.get("min_y", cy)), float(raw.get("max_y", cy))
        else:
            xs, ys = [float(p[0]) for p in box], [float(p[1]) for p in box]
            min_x, max_x, min_y, max_y = min(xs), max(xs), min(ys), max(ys)
            cx, cy = (min_x + max_x) / 2, (min_y + max_y) / 2
    except (TypeError, ValueError, IndexError, KeyError):
        return None
    return {**dict(raw), "text": text, "center_x": cx, "center_y": cy, "min_x": min_x, "max_x": max_x,
            "min_y": min_y, "max_y": max_y, "width": max(1, max_x-min_x), "height": max(1, max_y-min_y)}
