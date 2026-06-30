from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date
from typing import Iterable, Mapping

import pandas as pd

from src.database import fetch_all


def _trades(rows: Iterable[Mapping] | None = None) -> list[dict]:
    return [dict(row) for row in (fetch_all("trades", order_by="trade_date DESC") if rows is None else rows)]


def _done(row: Mapping) -> bool:
    return row.get("review_status") == "done" or bool(str(row.get("review_result") or "").strip())


def _planned(row: Mapping) -> bool:
    return bool(row.get("is_planned") or row.get("plan_id") or row.get("emotion") == "按计划")


def get_review_summary(rows: Iterable[Mapping] | None = None) -> dict:
    data = _trades(rows)
    done = [r for r in data if _done(r)]
    planned = [r for r in data if _planned(r)]
    due = [r for r in data if not _done(r) and r.get("review_status") != "ignored" and (not r.get("review_date") or str(r["review_date"]) <= date.today().isoformat())]
    avg = lambda key: round(sum(float(r[key]) for r in data if r.get(key) is not None) / max(sum(r.get(key) is not None for r in data), 1), 2)
    return {"total_trades": len(data), "reviewed_count": len(done), "pending_count": len(due), "planned_count": len(planned),
            "impulsive_count": len(data) - len(planned), "profit_count": sum(r.get("result_type") == "盈利" for r in done),
            "loss_count": sum(r.get("result_type") == "亏损" for r in done), "average_discipline_score": avg("discipline_score"),
            "average_confidence_score": avg("confidence_score")}


def get_monthly_review_stats(rows: Iterable[Mapping] | None = None) -> list[dict]:
    buckets: dict[str, dict] = {}
    for row in _trades(rows):
        month = str(row.get("trade_date") or "未知")[:7]
        item = buckets.setdefault(month, {"month": month, "trade_count": 0, "buy_amount": 0.0, "sell_amount": 0.0, "profit_count": 0, "loss_count": 0, "impulsive_count": 0})
        item["trade_count"] += 1
        amount = float(row.get("amount") or 0)
        if row.get("action") in {"买入", "补仓", "定投"}: item["buy_amount"] += amount
        if row.get("action") in {"卖出", "减仓"}: item["sell_amount"] += amount
        item["profit_count"] += row.get("result_type") == "盈利"
        item["loss_count"] += row.get("result_type") == "亏损"
        item["impulsive_count"] += not _planned(row)
    return [buckets[key] for key in sorted(buckets)]


def get_emotion_stats(rows: Iterable[Mapping] | None = None) -> list[dict]:
    buckets = defaultdict(list)
    for row in _trades(rows): buckets[row.get("emotion") or "未填写"].append(row)
    result = []
    for emotion, items in buckets.items():
        amounts = [float(r.get("result_amount") or 0) for r in items if r.get("result_amount") is not None]
        scores = [float(r["discipline_score"]) for r in items if r.get("discipline_score") is not None]
        result.append({"emotion": emotion, "trade_count": len(items), "profit_count": sum(r.get("result_type") == "盈利" for r in items),
                       "loss_count": sum(r.get("result_type") == "亏损" for r in items), "average_result_amount": round(sum(amounts) / len(amounts), 2) if amounts else 0,
                       "average_discipline_score": round(sum(scores) / len(scores), 2) if scores else 0})
    return result


def _tags(value) -> list[str]:
    if not value: return []
    if isinstance(value, list): return [str(v) for v in value]
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list): return [str(v) for v in parsed]
    except (json.JSONDecodeError, TypeError): pass
    return [part.strip() for part in str(value).replace("，", ",").split(",") if part.strip()]


def _tag_stats(key: str, rows=None) -> list[dict]:
    counts = Counter(tag for row in _trades(rows) for tag in _tags(row.get(key)))
    return [{"tag": tag, "count": count} for tag, count in counts.most_common()]


def get_mistake_tag_stats(rows: Iterable[Mapping] | None = None) -> list[dict]: return _tag_stats("mistake_tags", rows)
def get_success_tag_stats(rows: Iterable[Mapping] | None = None) -> list[dict]: return _tag_stats("success_tags", rows)


def generate_review_insights(rows: Iterable[Mapping] | None = None) -> list[str]:
    data, insights = _trades(rows), []
    summary = get_review_summary(data)
    if summary["total_trades"] and summary["impulsive_count"] / summary["total_trades"] > .3:
        insights.append("冲动操作占比偏高，建议交易前先写计划。")
    emotions = get_emotion_stats(data)
    panic = next((x for x in emotions if x["emotion"] == "恐慌"), None)
    if panic and panic["loss_count"] > panic["profit_count"]: insights.append("恐慌情绪下的交易亏损较多，建议设置冷静期。")
    planned_scores = [float(r["discipline_score"]) for r in data if _planned(r) and r.get("discipline_score")]
    impulse_scores = [float(r["discipline_score"]) for r in data if not _planned(r) and r.get("discipline_score")]
    if planned_scores and impulse_scores and sum(planned_scores)/len(planned_scores) > sum(impulse_scores)/len(impulse_scores):
        insights.append("按计划交易的纪律分高于临时交易，继续坚持先计划后执行。")
    if summary["pending_count"] > 3: insights.append("待复盘操作较多，建议先完成复盘再新增交易。")
    return insights or ["样本仍少，持续记录计划、情绪和结果后会形成更可靠的个人洞察。"]
