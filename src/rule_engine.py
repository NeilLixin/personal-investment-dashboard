from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Iterable, Mapping

from src.calculations import enrich_holdings, portfolio_summary, safe_float

ICONS = {"green": "🟢", "yellow": "🟡", "red": "🔴"}


def risk_item(key: str, level: str, title: str, description: str, evidence: str, suggestion: str, score: int) -> dict:
    return {"risk_key": key, "level": level, "icon": ICONS[level], "title": title, "description": description,
            "message": f"{description} {evidence}".strip(), "evidence": evidence, "suggestion": suggestion, "score": score}


def evaluate_risks(holdings: Iterable[Mapping], trades: Iterable[Mapping] = (), settings: Mapping | None = None) -> list[dict]:
    records, trades, settings = list(holdings), list(trades), dict(settings or {})
    frame = enrich_holdings(records)
    if frame.empty:
        return [risk_item("empty_portfolio", "green", "暂无持仓", "当前没有可分析的持仓数据。", "持仓数 0", "录入数据后再评估风险。", 0)]
    summary, risks = portfolio_summary(records), []
    total = max(float(frame["current_value"].sum()), 1)
    cash = summary["cash_ratio"]
    cash_red, cash_yellow = safe_float(settings.get("cash_red_ratio"), .10), safe_float(settings.get("cash_yellow_ratio"), .15)
    if cash < cash_red:
        risks.append(risk_item("cash_too_low", "red", "现金比例过低", "现金缓冲已跌破红线。", f"现金占比 {cash:.1%}，红线 {cash_red:.1%}", "暂停主动加仓，优先恢复现金。", 18))
    elif cash < cash_yellow:
        risks.append(risk_item("cash_too_low", "yellow", "现金比例偏低", "现金缓冲接近红线。", f"现金占比 {cash:.1%}", "谨慎安排新增仓位。", 8))
    elif cash > safe_float(settings.get("cash_high_ratio"), .40):
        risks.append(risk_item("cash_too_high", "yellow", "现金比例过高", "闲置现金比例较高。", f"现金占比 {cash:.1%}", "检查是否符合当前防守计划，不必为了降现金而交易。", 5))

    single_red, single_yellow = safe_float(settings.get("single_holding_red_ratio"), .25), safe_float(settings.get("single_holding_yellow_ratio"), .15)
    largest = frame.loc[frame["asset_ratio"].idxmax()]
    if largest["asset_ratio"] > single_yellow:
        level = "red" if largest["asset_ratio"] > single_red else "yellow"
        risks.append(risk_item("single_holding_too_high", level, "单一资产占比过高", "组合对单一资产较敏感。", f"{largest['name']} 占比 {largest['asset_ratio']:.1%}", "避免继续集中加仓，评估分散。", 16 if level == "red" else 7))

    type_ratios = frame.groupby("asset_type")["current_value"].sum() / total
    max_type, max_type_ratio = type_ratios.idxmax(), float(type_ratios.max())
    if max_type_ratio > safe_float(settings.get("asset_type_red_ratio"), .45):
        risks.append(risk_item("asset_type_too_high", "red", "单一资产类型占比过高", "资产类型集中度已超过红线。", f"{max_type} 占比 {max_type_ratio:.1%}", "新增资金优先考虑低配类型。", 14))

    high_ratio = float(frame.loc[frame["risk_level"] == "高", "current_value"].sum()) / total
    if high_ratio > safe_float(settings.get("high_risk_asset_red_ratio"), .50):
        risks.append(risk_item("high_risk_asset_too_high", "red", "高风险资产比例过高", "组合波动风险较高。", f"高风险资产占比 {high_ratio:.1%}", "降低高波动资产集中度。", 14))

    special = [("黄金", "gold_overweight", "黄金超配", safe_float(settings.get("gold_red_ratio"), .25)),
               ("A股科技/半导体/通信", "tech_overweight", "科技仓位超配", safe_float(settings.get("tech_red_ratio"), .35)),
               ("海外资产", "overseas_overweight", "海外资产超配", safe_float(settings.get("overseas_red_ratio"), .35))]
    for kind, key, title, limit in special:
        ratio = float(type_ratios.get(kind, 0))
        if ratio > limit:
            risks.append(risk_item(key, "red", title, f"{kind} 已超过配置上限。", f"占比 {ratio:.1%}，上限 {limit:.1%}", "避免追涨，按计划评估分批调整。", 12))

    losses = frame[frame["profit_amount"] < 0]
    if len(losses) > max(3, len(frame) / 2):
        risks.append(risk_item("loss_asset_too_many", "yellow", "亏损持仓数量过多", "多数持仓处于浮亏。", f"亏损 {len(losses)}/{len(frame)}", "逐项检查原始逻辑，避免盲目补仓。", 7))
    if not frame.empty and float(frame["profit_rate"].min()) < -.20:
        row = frame.loc[frame["profit_rate"].idxmin()]
        risks.append(risk_item("large_loss_holding", "red", "单一持仓亏损过大", "存在显著回撤持仓。", f"{row['name']} 收益率 {row['profit_rate']:.1%}", "复核止损与仓位纪律。", 12))

    cutoff = date.today() - timedelta(days=7)
    recent = [t for t in trades if _date(t.get("trade_date")) and _date(t.get("trade_date")) >= cutoff]
    freq_yellow, freq_red = int(settings.get("weekly_trade_warning", 8)), int(settings.get("weekly_trade_red", 15))
    if len(recent) > freq_yellow:
        level = "red" if len(recent) > freq_red else "yellow"
        risks.append(risk_item("frequent_trading", level, "近期操作过于频繁", "近 7 天交易频率偏高。", f"共 {len(recent)} 次", "减少临时决策，优先执行计划。", 12 if level == "red" else 6))
    impulse = [t for t in recent if t.get("emotion") == "冲动" or not bool(t.get("is_planned", t.get("plan_id")))]
    impulse_ratio = len(impulse) / len(recent) if recent else 0
    impulse_yellow, impulse_red = safe_float(settings.get("impulse_warning_ratio"), .30), safe_float(settings.get("impulse_red_ratio"), .50)
    if recent and impulse_ratio > impulse_yellow:
        level = "red" if impulse_ratio > impulse_red else "yellow"
        risks.append(risk_item("impulsive_trading_too_many", level, "冲动操作过多", "近期非计划操作占比较高。", f"占比 {impulse_ratio:.1%}", "交易前先写计划并设置冷静期。", 12 if level == "red" else 6))
    pending = [t for t in trades if t.get("review_status", "pending") == "pending" and t.get("review_date") and str(t["review_date"]) <= date.today().isoformat() and not t.get("review_result")]
    if len(pending) > 5:
        level = "red" if len(pending) > 10 else "yellow"
        risks.append(risk_item("pending_reviews_too_many", level, "待复盘过多", "到期复盘积压。", f"待复盘 {len(pending)} 条", "先完成复盘再新增交易。", 10 if level == "red" else 5))
    enabled_plans = int(settings.get("enabled_plan_count", 0))
    if cash < cash_red and enabled_plans > 3:
        risks.append(risk_item("no_cash_but_many_plans", "yellow", "现金不足但计划较多", "补仓计划可能超过现金承受力。", f"启用计划 {enabled_plans} 个", "为计划设置资金上限。", 6))
    no_plan = [t for t in recent if not t.get("plan_id") and not t.get("is_planned")]
    if len(no_plan) >= 3:
        risks.append(risk_item("no_plan_recent_trade", "yellow", "最近交易缺少计划关联", "多笔交易没有计划依据。", f"近 7 天 {len(no_plan)} 笔", "先建立计划，再执行交易。", 6))
    hhi = float((frame["asset_ratio"] ** 2).sum())
    if hhi > .30:
        risks.append(risk_item("concentration_risk", "red", "资产集中度过高", "组合集中度指数偏高。", f"HHI {hhi:.2f}", "降低头部持仓权重。", 12))
    if not risks:
        risks.append(risk_item("portfolio_normal", "green", "风险正常", "当前未触发主要风险规则。", "风险分 0", "保持记录并按计划复盘。", 0))
    return sorted(risks, key=lambda x: ({"red": 0, "yellow": 1, "green": 2}[x["level"]], -x["score"]))


def _date(value) -> date | None:
    try: return datetime.fromisoformat(str(value)).date()
    except (TypeError, ValueError): return None


def risk_summary(items: Iterable[Mapping]) -> dict:
    rows = list(items)
    score = min(100, sum(int(row.get("score", 0)) for row in rows))
    level = "red" if score >= 61 else "yellow" if score >= 31 else "green"
    return {"risk_score": score, "level": level, "red_count": sum(r.get("level") == "red" for r in rows),
            "yellow_count": sum(r.get("level") == "yellow" for r in rows), "green_count": sum(r.get("level") == "green" for r in rows)}


def system_suggestions(holdings: Iterable[Mapping], trades: Iterable[Mapping] = ()) -> list[str]:
    return [f"{item['icon']} {item['suggestion']}" for item in evaluate_risks(holdings, trades)[:5]]
