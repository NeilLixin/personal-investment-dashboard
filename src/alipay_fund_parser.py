from __future__ import annotations

import re
from typing import Any, Iterable, Mapping


FUND_KEYWORDS = (
    "混合", "指数", "债券", "股票", "QDII", "FOF", "ETF", "联接", "精选", "成长",
    "主题", "标普", "纳斯达克", "中证", "全球", "科技", "设备", "优选", "先锋", "汇宏",
)
IGNORE_EXACT = {
    "基金", "我的持有", "全部", "偏股", "偏债", "指数", "黄金", "全球", "名称",
    "金额/昨日收益", "持有收益/率", "基金市场", "机会", "自选", "持有", "金额排序",
    "排序", "图标", "定投",
}
IGNORE_PREFIXES = ("市场解读", "产品提醒")
SIGN_TRANSLATION = str.maketrans({
    "＋": "+", "﹢": "+", "十": "+", "—": "-", "－": "-", "一": "-", "，": ",", "％": "%",
})
CONTINUATION_PATTERN = re.compile(r"^[（(]?(?:QDII|FOF|ETF)(?:[-/][A-Z]+)*[）)]?[A-Z]?$", re.IGNORECASE)


def parse_alipay_fund_holdings_from_ocr_items(
    items: Iterable[Mapping[str, Any]] | None,
    image_width: float | None = None,
    image_height: float | None = None,
) -> dict[str, Any]:
    """Parse Alipay's three-column holdings table from OCR boxes."""
    debug: dict[str, Any] = {
        "item_count": 0,
        "name_candidates": [],
        "amount_candidates": [],
        "row_groups": [],
        "ignored_items": [],
        "warnings": [],
    }
    normalized = [_normalize_item(item) for item in (items or [])]
    normalized = [item for item in normalized if item and item["text"]]
    normalized.sort(key=lambda item: (item["center_y"], item["center_x"]))
    debug["item_count"] = len(normalized)
    if not normalized:
        return {"ok": False, "holdings": [], "debug": debug, "error": "OCR items 为空"}

    width = float(image_width or _infer_width(normalized))
    if width <= 0:
        return {"ok": False, "holdings": [], "debug": debug, "error": "无法推断截图宽度"}

    usable: list[dict[str, Any]] = []
    for item in normalized:
        if _is_ignored(item["text"]):
            debug["ignored_items"].append(item["text"])
        else:
            usable.append(item)

    name_candidates = [
        item for item in usable
        if item["center_x"] < width * 0.45 and _is_fund_name(item["text"])
    ]
    debug["name_candidates"] = [item["text"] for item in name_candidates]
    debug["amount_candidates"] = [
        item["text"] for item in usable if _parse_numeric(item["text"]) is not None
    ]
    if not name_candidates:
        return {
            "ok": False,
            "holdings": [],
            "debug": debug,
            "error": "没有识别到基金名称候选，请确认截图包含“我的持有”列表",
        }

    holdings: list[dict[str, Any]] = []
    for index, name_item in enumerate(name_candidates):
        row_start = name_item["center_y"] - max(16.0, name_item["height"] * 0.7)
        next_y = name_candidates[index + 1]["center_y"] if index + 1 < len(name_candidates) else None
        row_end = (next_y - max(16.0, name_item["height"] * 0.5)) if next_y is not None else float("inf")
        row_items = [item for item in usable if row_start <= item["center_y"] < row_end]
        name = _join_name(name_item, row_items, width)
        middle_numbers = _column_numbers(row_items, width, "middle")
        right_numbers = _column_numbers(row_items, width, "right")
        current_value = _first_number(middle_numbers, percent=False, position=0)
        yesterday_profit = _first_number(middle_numbers, percent=False, position=1)
        profit_amount = _first_number(right_numbers, percent=False, position=0)
        profit_rate = _first_number(right_numbers, percent=True, position=0)
        row_debug = {
            "name": name,
            "range": [row_start, None if row_end == float("inf") else row_end],
            "middle": [item["text"] for item in middle_numbers],
            "right": [item["text"] for item in right_numbers],
        }
        debug["row_groups"].append(row_debug)
        missing = [
            field for field, value in (
                ("current_value", current_value),
                ("yesterday_profit", yesterday_profit),
                ("profit_amount", profit_amount),
                ("profit_rate", profit_rate),
            ) if value is None
        ]
        if missing:
            debug["warnings"].append(f"{name} 缺少字段：{', '.join(missing)}")
            continue
        asset_type, market = infer_fund_classification(name)
        holdings.append({
            "name": name,
            "code": "",
            "platform": "支付宝",
            "asset_type": asset_type,
            "market": market,
            "current_value": current_value,
            "cost_amount": round(current_value - profit_amount, 2),
            "profit_amount": profit_amount,
            "profit_rate": profit_rate,
            "yesterday_profit": yesterday_profit,
            "holding_share": None,
            "latest_price": None,
            "risk_level": "中",
            "note": "支付宝基金截图导入",
        })

    if not holdings:
        return {
            "ok": False,
            "holdings": [],
            "debug": debug,
            "error": "识别到了基金名称，但没有任何一行同时匹配四个金额字段",
        }
    if len(holdings) < len(name_candidates):
        debug["warnings"].append("部分基金行字段不完整，已留待调试和人工确认")
    return {"ok": True, "holdings": holdings, "debug": debug, "error": ""}


def infer_fund_classification(name: str) -> tuple[str, str]:
    source = name.upper()
    if any(key in source for key in ("QDII", "全球", "标普", "纳斯达克", "美股")):
        return "海外资产", "海外"
    if "黄金" in source:
        return "黄金", "黄金"
    if any(key in source for key in ("半导体", "芯片", "科技", "通信", "电网设备", "新能源")):
        return "A股科技/半导体/通信", "A股"
    if any(key in source for key in ("沪深300", "中证A500", "创业板", "宽基", "500")):
        return "A股宽基", "A股"
    if "债" in source:
        return "债券/固收", "其他"
    return "其他", "A股"


def _normalize_item(raw: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(raw, Mapping):
        return None
    text = re.sub(r"\s+", " ", str(raw.get("text") or raw.get("txt") or "")).strip()
    try:
        center_x = float(raw.get("center_x"))
        center_y = float(raw.get("center_y"))
    except (TypeError, ValueError):
        box = raw.get("box") or []
        try:
            xs = [float(point[0]) for point in box]
            ys = [float(point[1]) for point in box]
            center_x, center_y = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        except (TypeError, ValueError, IndexError):
            return None
    min_y = _as_float(raw.get("min_y"), center_y)
    max_y = _as_float(raw.get("max_y"), center_y)
    return {
        **dict(raw),
        "text": text,
        "center_x": center_x,
        "center_y": center_y,
        "max_x": _as_float(raw.get("max_x"), center_x),
        "height": max(1.0, max_y - min_y),
    }


def _infer_width(items: list[dict[str, Any]]) -> float:
    return max((max(item["max_x"], item["center_x"] * 1.08) for item in items), default=0.0)


def _is_ignored(text: str) -> bool:
    compact = text.strip()
    if compact in IGNORE_EXACT or any(compact.startswith(prefix) for prefix in IGNORE_PREFIXES):
        return True
    if re.fullmatch(r"[+\-↑↓△▽<>◇◆·•\s]+", compact):
        return True
    if re.fullmatch(r"\d{1,2}:\d{2}", compact):
        return True
    return False


def _is_fund_name(text: str) -> bool:
    upper = text.upper()
    return not CONTINUATION_PATTERN.fullmatch(upper) and any(keyword.upper() in upper for keyword in FUND_KEYWORDS)


def _join_name(name_item: dict[str, Any], row_items: list[dict[str, Any]], width: float) -> str:
    parts = [name_item["text"]]
    continuations = [
        item for item in row_items
        if item is not name_item
        and item["center_x"] < width * 0.45
        and item["center_y"] > name_item["center_y"]
        and item["center_y"] - name_item["center_y"] <= max(120.0, name_item["height"] * 3.5)
        and CONTINUATION_PATTERN.fullmatch(item["text"].upper())
    ]
    parts.extend(item["text"] for item in sorted(continuations, key=lambda item: item["center_y"]))
    return "".join(parts).replace("（", "(").replace("）", ")").replace("F0F", "FOF").replace("f0f", "FOF").replace(" ", "")


def _column_numbers(row_items: list[dict[str, Any]], width: float, column: str) -> list[dict[str, Any]]:
    if column == "middle":
        selected = [
            item for item in row_items
            if width * 0.40 <= item["center_x"] < width * 0.68 and _parse_numeric(item["text"]) is not None
        ]
    else:
        selected = [
            item for item in row_items
            if item["center_x"] >= width * 0.68 and _parse_numeric(item["text"]) is not None
        ]
    return sorted(selected, key=lambda item: (item["center_y"], item["center_x"]))


def _first_number(items: list[dict[str, Any]], percent: bool, position: int) -> float | None:
    matches = [item for item in items if ("%" in _normalize_numeric_text(item["text"])) is percent]
    if position >= len(matches):
        return None
    return _parse_numeric(matches[position]["text"])


def _normalize_numeric_text(value: str) -> str:
    text = value.translate(SIGN_TRANSLATION).replace(" ", "").replace("¥", "").replace("￥", "")
    if re.fullmatch(r"[+\-]?[\dOolI,]+(?:\.[\dOolI]+)?%?", text, re.IGNORECASE):
        text = text.replace("O", "0").replace("o", "0").replace("l", "1").replace("I", "1")
    return text


def _parse_numeric(value: str) -> float | None:
    text = _normalize_numeric_text(value)
    if not re.fullmatch(r"[+\-]?\d[\d,]*(?:\.\d+)?%?", text):
        return None
    try:
        return float(text.replace(",", "").replace("%", ""))
    except ValueError:
        return None


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
