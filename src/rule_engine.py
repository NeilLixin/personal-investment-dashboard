from __future__ import annotations

from datetime import date
from typing import Iterable, Mapping

from src.calculations import enrich_holdings, portfolio_summary, safe_float


def risk_item(level: str, title: str, message: str, suggestion: str) -> dict[str, str]:
    icons = {"normal": "🟢", "warning": "🟡", "danger": "🔴"}
    return {"level": level, "icon": icons[level], "title": title, "message": message, "suggestion": suggestion}


def evaluate_risks(
    holdings: Iterable[Mapping],
    trades: Iterable[Mapping] = (),
    settings: Mapping | None = None,
) -> list[dict[str, str]]:
    records = list(holdings)
    frame = enrich_holdings(records)
    if frame.empty:
        return [risk_item("warning", "暂无持仓", "还没有可分析的资产数据。", "先录入持仓或导入截图。")]
    settings = settings or {}
    summary = portfolio_summary(records)
    risks: list[dict[str, str]] = []
    cash_floor = safe_float(settings.get("cash_min_ratio"), 0.10)
    if summary["cash_ratio"] < cash_floor:
        risks.append(risk_item("danger", "现金比例过低", f"现金占比 {summary['cash_ratio']:.1%}，低于 {cash_floor:.0%}。", "暂停主动加仓，优先恢复现金缓冲。"))
    max_single = safe_float(settings.get("single_asset_max_ratio"), 0.25)
    for _, row in frame.iterrows():
        if row["asset_ratio"] > max_single:
            risks.append(risk_item("danger", "单一资产占比过高", f"{row['name']} 占比 {row['asset_ratio']:.1%}。", "避免继续集中加仓，评估分批降低仓位。"))
    type_ratios = frame.groupby("asset_type")["current_value"].sum() / max(frame["current_value"].sum(), 1)
    type_limit = safe_float(settings.get("single_type_max_ratio"), 0.40)
    for asset_type, ratio in type_ratios.items():
        if ratio > type_limit:
            risks.append(risk_item("warning", "资产类型集中", f"{asset_type} 占比 {ratio:.1%}。", "新增资金优先分散到低配资产。"))
    high_risk_ratio = frame.loc[frame["risk_level"] == "高", "current_value"].sum() / max(frame["current_value"].sum(), 1)
    if high_risk_ratio > safe_float(settings.get("high_risk_max_ratio"), 0.35):
        risks.append(risk_item("danger", "高风险仓位偏高", f"高风险资产占比 {high_risk_ratio:.1%}。", "降低追涨频率，先处理高波动集中仓位。"))
    for asset_type, title in (("黄金", "黄金仓位超过目标"), ("A股科技/半导体/通信", "科技仓位超过目标")):
        subset = frame[frame["asset_type"] == asset_type]
        if not subset.empty and subset["current_value"].sum() / frame["current_value"].sum() > subset["target_max_ratio"].max():
            risks.append(risk_item("warning", title, f"{asset_type} 已超过目标上限。", "优先观察反弹减仓，不建议继续追涨。"))
    loss_ratio = (frame["profit_amount"] < 0).mean()
    if loss_ratio >= 0.5:
        risks.append(risk_item("warning", "浮亏资产较多", f"{loss_ratio:.0%} 的持仓处于浮亏。", "逐项检查买入逻辑，不要仅因浮亏盲目补仓。"))
    current_month = date.today().strftime("%Y-%m")
    month_trades = [row for row in trades if str(row.get("trade_date", "")).startswith(current_month)]
    if len(month_trades) > int(settings.get("monthly_trade_warning", 12)):
        risks.append(risk_item("warning", "操作过于频繁", f"本月已经操作 {len(month_trades)} 次。", "减少临时决策，优先执行已有计划。"))
    if not risks:
        risks.append(risk_item("normal", "风险正常", "当前未触发主要仓位风险规则。", "保持记录，按计划复盘。"))
    order = {"danger": 0, "warning": 1, "normal": 2}
    return sorted(risks, key=lambda item: order[item["level"]])


def system_suggestions(holdings: Iterable[Mapping], trades: Iterable[Mapping] = ()) -> list[str]:
    return [f"{item['icon']} {item['suggestion']}" for item in evaluate_risks(holdings, trades)[:5]]
