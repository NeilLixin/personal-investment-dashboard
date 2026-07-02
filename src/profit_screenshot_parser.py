from __future__ import annotations

import re
from datetime import date
from difflib import SequenceMatcher
from typing import Any, Iterable, Mapping

from src.calculations import safe_float
from src.import_service import normalize_holding_key
from src.fund_code_service import match_fund_code_by_name


NUMBER = r"[+＋\-−－]?\s*[¥￥]?\s*[\d,]+(?:\.\d+)?"


def _clean(text: str) -> str:
    return str(text or "").replace("−", "-").replace("－", "-").replace("＋", "+").replace("￥", "¥").replace("％", "%")


def _number(value: Any) -> float | None:
    if value in (None, ""): return None
    match = re.search(NUMBER, _clean(str(value)))
    if not match: return None
    cleaned = re.sub(r"[^\d.+-]", "", match.group()).replace("+", "")
    try: return float(cleaned)
    except ValueError: return None


def _after_label(text: str, labels: Iterable[str], percent: bool = False) -> float | None:
    for label in labels:
        match = re.search(rf"{re.escape(label)}\s*[:：]?\s*({NUMBER})\s*{'%' if percent else ''}", text, re.I)
        if match:
            value = _number(match.group(1)); return value / 100 if percent and value is not None else value
    return None


def detect_profit_screenshot_source(text: str) -> str:
    value = _clean(text).lower()
    if "支付宝" in value or "蚂蚁财富" in value: return "alipay_profit"
    if "天天基金" in value: return "tiantian_profit"
    if "东方财富" in value or "东财" in value: return "eastmoney_profit"
    return "unknown_profit"


def parse_profit_screenshot_text(text: str, source: str | None = None) -> dict[str, Any]:
    normalized = _clean(text)
    if not normalized.strip():
        return {"ok":False, "source":source or "unknown_profit", "account":{}, "items":[], "warnings":["OCR 原文为空，请重新识别或手动粘贴文字。"]}
    source = source or detect_profit_screenshot_source(normalized); warnings: list[str] = []
    account = {
        "account_name": source.replace("_profit", ""),
        "total_assets": _after_label(normalized, ("账户资产", "总资产", "资产金额")),
        "daily_pnl": _after_label(normalized, ("当日收益", "今日收益")),
        "fund_count": int(v) if (v := _after_label(normalized, ("基金数量", "只基金"))) is not None else None,
        "snapshot_date": None,
    }
    count_match = re.search(r"(\d+)\s*只基金", normalized)
    if count_match: account["fund_count"] = int(count_match.group(1))
    date_match = re.search(r"日期\s*[:：]?\s*((?:0?[1-9]|1[0-2])[-/.](?:0?[1-9]|[12]\d|3[01]))", normalized)
    if date_match: account["snapshot_date"] = date_match.group(1).replace("/", "-").replace(".", "-")
    code_matches = list(re.finditer(r"(?<!\d)(\d{6})(?!\d)", normalized)); items = []
    for index, match in enumerate(code_matches):
        start = code_matches[index-1].end() if index else 0; end = code_matches[index+1].start() if index+1 < len(code_matches) else len(normalized)
        before = normalized[start:match.start()]; after = normalized[match.end():end]; block = before + "\n" + match.group(1) + "\n" + after
        lines = [line.strip() for line in before.splitlines() if line.strip()]
        excluded = ("基金名称", "涨跌幅", "当日收益", "持有收益", "账户资产", "总资产", "只基金", "日期", "支付宝", "天天基金", "东方财富")
        name = next((line for line in reversed(lines) if not any(word in line for word in excluded) and not re.fullmatch(NUMBER+r"%?", line)), "")
        item = normalize_profit_item({
            "code":match.group(1), "name":name, "raw_name":name, "raw_text":block,
            "market_value":_after_label(after, ("资产金额", "持有金额", "金额", "已更新")),
            "change_pct":_after_label(after, ("涨跌幅", "日增长率"), True),
            "latest_nav":_after_label(after, ("最新净值", "最新值", "估算值", "单位净值")),
            "daily_pnl":_after_label(after, ("当日收益", "今日收益")),
            "holding_pnl":_after_label(after, ("持有收益", "累计收益")),
            "holding_return_pct":_after_label(after, ("持有收益率", "收益率"), True),
            "tags":[],
        })
        if not name: warnings.append(f"代码 {item['code']} 未识别到完整名称，将优先按代码匹配。")
        if all(item.get(key) is None for key in ("change_pct","daily_pnl","holding_pnl","market_value")):
            warnings.append(f"代码 {item['code']} 缺少收益字段，请在确认表中补充。")
        items.append(item)
    if not items: warnings.append("没有识别到 6 位基金代码，请检查 OCR 原文或手动补充。")
    if account["fund_count"] is not None and account["fund_count"] != len(items): warnings.append("截图基金数量与解析条数不一致，可能只识别了部分内容。")
    return {"ok":bool(items), "source":source, "account":account, "items":items, "warnings":warnings}


def normalize_profit_item(item: Mapping) -> dict[str, Any]:
    result = dict(item); result["code"] = re.sub(r"\D", "", str(result.get("code") or ""))[:6]
    for key in ("market_value","latest_nav","daily_pnl","holding_pnl"):
        if result.get(key) is not None: result[key] = _number(result[key])
    for key in ("change_pct","holding_return_pct"):
        value = result.get(key)
        if value is not None:
            value = _number(value); result[key] = value / 100 if value is not None and abs(value) > 1 else value
    result["name"] = re.sub(r"\s+", "", str(result.get("name") or "")).strip()
    return result


def match_profit_items_to_holdings(items: Iterable[Mapping], holdings: Iterable[Mapping]) -> list[dict[str, Any]]:
    holding_rows = [dict(h) for h in holdings]; matched = []
    for source in items:
        item = dict(source); code = str(item.get("code") or "").strip()
        candidates = [h for h in holding_rows if code and str(h.get("code") or "").strip() == code]
        target = candidates[0] if len(candidates) == 1 else None
        if target is None and item.get("name") and "..." not in item["name"] and "…" not in item["name"]:
            needle = _normalized_name(item["name"]); scored = sorted(((SequenceMatcher(None, needle, _normalized_name(h.get("name"))).ratio(), h) for h in holding_rows), reverse=True, key=lambda x:x[0])
            if scored and scored[0][0] >= .84 and (len(scored) == 1 or scored[0][0] - scored[1][0] >= .08): target = scored[0][1]
        item.update({"holding_id":target.get("id") if target else None, "holding_name":target.get("name") if target else "",
                     "match_status":"已匹配" if target else "未匹配", "import":bool(target)})
        matched.append(item)
    return matched


def recommend_profit_item_codes(items: Iterable[Mapping], candidates: Iterable[Mapping]) -> list[dict[str, Any]]:
    result = []
    for source in items:
        item = dict(source)
        match = match_fund_code_by_name(item.get("name", ""), candidates) if not item.get("code") else {"status":"screenshot_code", "best":None}
        best = match.get("best") or {}
        item.update({"recommended_code":item.get("code") or best.get("code", ""), "recommended_name":best.get("name", ""),
                     "code_match_status":match["status"], "confirm_code_fill":False})
        result.append(item)
    return result


def build_market_snapshot_from_profit_item(item: Mapping, holding: Mapping, source: str | None = None) -> dict[str, Any]:
    source_key = source or str(item.get("source") or "unknown_profit")
    source_names = {"alipay_profit":"alipay_profit_screenshot", "tiantian_profit":"tiantian_profit_screenshot", "eastmoney_profit":"eastmoney_profit_screenshot"}
    return {"holding_id":holding.get("id"), "platform":holding.get("platform"), "code":holding.get("code") or item.get("code"),
            "name":holding.get("name"), "asset_type":holding.get("asset_type"), "source":"screenshot",
            "source_name":source_names.get(source_key, "profit_screenshot"), "snapshot_date":date.today().isoformat(),
            "nav":item.get("latest_nav"), "change_pct":item.get("change_pct"), "daily_pnl":item.get("daily_pnl"),
            "daily_pnl_estimated":0 if item.get("daily_pnl") is not None else 1, "holding_pnl":item.get("holding_pnl"),
            "holding_return_pct":item.get("holding_return_pct"), "market_value":item.get("market_value"),
            "shares":holding.get("holding_share"), "status":"manual_confirmed", "quality_level":"third_party_estimate",
            "raw_payload":dict(item)}


def _normalized_name(value: Any) -> str:
    return normalize_holding_key({"platform":"", "name":str(value or "")}).split("NAME:", 1)[-1]
