from __future__ import annotations

import re
from typing import Any


NUMBER = r"[-+]?\s*[¥￥]?\s*[\d,]+(?:\.\d+)?"


def parse_number(value: str | None) -> float | None:
    if not value:
        return None
    match = re.search(NUMBER, value)
    if not match:
        return None
    try:
        return float(re.sub(r"[^\d.\-+]", "", match.group(0)).replace("+", ""))
    except ValueError:
        return None


def infer_asset_type(name: str, text: str = "") -> tuple[str, str]:
    source = f"{name} {text}".lower()
    if any(key in source for key in ("黄金", "积存金", "金价")):
        return "黄金", "黄金"
    if any(key in source for key in ("纳斯达克", "标普", "海外", "qdii")):
        return "海外资产", "美股"
    if any(key in source for key in ("半导体", "芯片", "通信", "科技", "创业板")):
        return "A股科技/半导体/通信", "A股"
    if any(key in source for key in ("债", "固收", "理财")):
        return "债券/固收", "其他"
    if any(key in source for key in ("现金", "余额", "货币")):
        return "现金", "现金"
    if any(key in source for key in ("沪深", "中证", "a500", "宽基", "上证")):
        return "A股宽基", "A股"
    return "其他", "其他"


def _value_after_label(lines: list[str], index: int, labels: tuple[str, ...]) -> str:
    line = lines[index]
    for label in labels:
        if label in line:
            inline = line.split(label, 1)[1].strip(" ：:")
            if inline:
                return inline
            if index + 1 < len(lines):
                return lines[index + 1]
    return ""


def _split_product_blocks(lines: list[str]) -> list[list[str]]:
    starts = []
    for index, line in enumerate(lines):
        if re.search(r"^(产品名称|基金名称|理财名称|资产名称)\s*[:：]?", line):
            starts.append(index)
        elif index + 1 < len(lines) and "持有金额" in lines[index + 1] and not re.search(NUMBER, line):
            starts.append(index)
    if not starts:
        return [lines]
    blocks = []
    for position, start in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else len(lines)
        blocks.append(lines[start:end])
    return blocks


def _parse_block(lines: list[str]) -> dict[str, Any] | None:
    labels = {
        "name": ("产品名称", "基金名称", "理财名称", "资产名称"),
        "current_value": ("持有金额", "当前市值", "总资产"),
        "profit_amount": ("持有收益", "累计收益", "浮盈亏"),
        "profit_rate": ("收益率", "持有收益率"),
        "yesterday_profit": ("昨日收益",),
        "holding_share": ("持有份额", "黄金克数", "持有克数"),
        "latest_price": ("最新净值", "最新金价", "金价"),
        "code": ("基金代码", "产品代码"),
    }
    result: dict[str, Any] = {key: None for key in labels}
    for index, line in enumerate(lines):
        for field, field_labels in labels.items():
            if any(label in line for label in field_labels):
                value = _value_after_label(lines, index, field_labels)
                result[field] = value if field in {"name", "code"} else parse_number(value)
    if not result["name"]:
        candidates = [line for line in lines if not any(label in line for values in labels.values() for label in values)]
        result["name"] = next((line for line in candidates if 2 <= len(line) <= 40 and not re.search(r"^[-+¥￥\d,.%]+$", line)), None)
    if not result["name"] or result["current_value"] is None:
        return None
    if result["profit_rate"] is not None:
        result["profit_rate"] /= 100
    profit = result["profit_amount"] or 0.0
    result["cost_amount"] = round((result["current_value"] or 0.0) - profit, 2)
    asset_type, market = infer_asset_type(result["name"], " ".join(lines))
    result.update({"asset_type": asset_type, "market": market, "platform": "支付宝", "note": "支付宝截图 OCR 导入"})
    return result


def parse_alipay_text(text: str) -> list[dict[str, Any]]:
    normalized = text.replace("％", "%").replace("，", ",")
    lines = [re.sub(r"\s+", " ", line).strip() for line in normalized.splitlines() if line.strip() and not line.startswith("## ")]
    results = []
    for block in _split_product_blocks(lines):
        parsed = _parse_block(block)
        if parsed:
            results.append(parsed)
    return results
