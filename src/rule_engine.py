from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Iterable, Mapping

from src.calculations import enrich_holdings, portfolio_summary, safe_float

ICONS = {"green": "🟢", "yellow": "🟡", "red": "🔴"}
CATEGORY_WEIGHTS = {"仓位风险": 35, "收益风险": 20, "交易行为风险": 20, "复盘纪律风险": 15, "数据质量风险": 10}


def risk_item(key: str, category: str, level: str, title: str, description: str,
              evidence: str, suggestion: str, score: int) -> dict:
    return {"risk_key": key, "category": category, "level": level, "icon": ICONS[level], "title": title,
            "description": description, "message": f"{description} {evidence}".strip(), "evidence": evidence,
            "suggestion": suggestion, "score": score}


def evaluate_risks(holdings: Iterable[Mapping], trades: Iterable[Mapping] = (), settings: Mapping | None = None,
                   plans: Iterable[Mapping] = (), sync_status: Mapping | None = None,
                   market_snapshots: Iterable[Mapping] | None = None, **kwargs) -> list[dict]:
    records, trades, plans, settings = list(holdings), list(trades), list(plans), dict(settings or {})
    frame, risks = enrich_holdings(records), []
    add = lambda *args: risks.append(risk_item(*args))
    if frame.empty:
        add("empty_portfolio", "数据质量风险", "green", "暂无持仓", "当前没有可分析的持仓数据。", "持仓数 0", "录入持仓后再评估风险。", 0)
        return risks
    total = max(float(frame["current_value"].sum()), 1)
    cash = portfolio_summary(records)["cash_ratio"]
    if cash <= .05: add("cash_too_low", "仓位风险", "red", "现金比例过低", "现金缓冲低于红线。", f"当前现金 {cash:.1%}，低于红线 5%", "暂停主动加仓，优先恢复现金。", 12)
    elif cash < .10: add("cash_too_low", "仓位风险", "yellow", "现金比例偏低", "现金缓冲不足。", f"当前现金 {cash:.1%}", "控制新增仓位，预留应急资金。", 6)
    largest = frame.loc[frame["asset_ratio"].idxmax()]
    if largest["asset_ratio"] > .20:
        level = "red" if largest["asset_ratio"] > .30 else "yellow"
        add("single_holding_too_high", "仓位风险", level, "单一资产占比过高", "组合对单一资产较敏感。",
            f"{largest['name']} 占比 {largest['asset_ratio']:.1%}", "避免继续集中加仓，评估分散。", 10 if level == "red" else 5)
    type_ratios = frame.groupby("asset_type")["current_value"].sum() / total
    if not type_ratios.empty and float(type_ratios.max()) > .35:
        kind, ratio = type_ratios.idxmax(), float(type_ratios.max()); level = "red" if ratio > .50 else "yellow"
        add("asset_type_too_high", "仓位风险", level, "单一资产类型占比过高", "资产类型集中度偏高。", f"{kind} 占比 {ratio:.1%}", "新增资金优先考虑低配类型。", 8 if level == "red" else 4)
    high_ratio = float(frame.loc[frame.get("risk_level") == "高", "current_value"].sum()) / total
    if high_ratio > .40:
        level = "red" if high_ratio > .60 else "yellow"
        add("high_risk_asset_too_high", "仓位风险", level, "高风险资产比例过高", "组合波动承受要求较高。", f"高风险资产 {high_ratio:.1%}", "降低高波动资产集中度。", 7 if level == "red" else 4)
    for kind, key, title, yellow, red in (("黄金", "gold_overweight", "黄金超配", .15, .25), ("海外资产", "overseas_overweight", "海外资产超配", .30, .40), ("A股科技/半导体/通信", "tech_overweight", "科技仓位超配", .25, .40)):
        ratio = float(type_ratios.get(kind, 0))
        if ratio > yellow:
            level = "red" if ratio > red else "yellow"
            add(key, "仓位风险", level, title, f"{kind} 超过建议区间。", f"当前占比 {ratio:.1%}", "避免追涨，按计划评估调整。", 7 if level == "red" else 3)

    losses = frame[frame["profit_amount"] < 0]
    for _, row in frame[frame["profit_rate"] < -.08].iterrows():
        level = "red" if row["profit_rate"] < -.15 else "yellow"
        add(f"large_loss_{row.get('id', row['name'])}", "收益风险", level, "单一持仓浮亏过大", "持仓回撤需要复核。", f"{row['name']} 收益率 {row['profit_rate']:.1%}", "复核持有逻辑、仓位和退出纪律。", 8 if level == "red" else 4)
    if len(losses) > len(frame) / 2:
        add("loss_asset_too_many", "收益风险", "yellow", "亏损持仓数量过多", "半数以上持仓处于浮亏。", f"亏损 {len(losses)}/{len(frame)}", "逐项复核，不因亏损机械补仓。", 5)
    positive = frame.loc[frame["profit_amount"] > 0, "profit_amount"]
    if positive.sum() > 0 and float(positive.max()/positive.sum()) > .70:
        add("profit_concentrated", "收益风险", "yellow", "盈利集中在少数资产", "组合利润来源较集中。", f"最大盈利贡献 {positive.max()/positive.sum():.1%}", "不要把单一资产盈利当作组合稳定性。", 4)
    for kind, group in frame.groupby("asset_type"):
        if len(group) >= 2 and float(group["profit_amount"].sum()) < 0:
            add(f"type_loss_{kind}", "收益风险", "yellow", "某类资产整体亏损", "同类资产可能存在共振风险。", f"{kind} 合计浮亏 ¥{group['profit_amount'].sum():,.2f}", "检查该类资产总暴露而非逐只补仓。", 3)

    today = date.today(); recent7 = [t for t in trades if (_date(t.get("trade_date")) or date.min) >= today-timedelta(days=7)]
    recent30 = [t for t in trades if (_date(t.get("trade_date")) or date.min) >= today-timedelta(days=30)]
    if len(recent7) >= 5:
        level = "red" if len(recent7) > 10 else "yellow"; add("trade_7d", "交易行为风险", level, "最近 7 天操作过多", "短期交易频率偏高。", f"近 7 天 {len(recent7)} 次", "减少临时决策，优先执行既定计划。", 8 if level == "red" else 4)
    if len(recent30) >= 15:
        level = "red" if len(recent30) > 30 else "yellow"; add("trade_30d", "交易行为风险", level, "最近 30 天操作过多", "月度操作频率偏高。", f"近 30 天 {len(recent30)} 次", "合并同方向操作并设置冷静期。", 6 if level == "red" else 3)
    impulse = [t for t in recent30 if t.get("emotion") == "冲动"]
    if recent30 and len(impulse)/len(recent30) >= .30:
        ratio = len(impulse)/len(recent30); level = "red" if ratio > .50 else "yellow"; add("impulse", "交易行为风险", level, "冲动操作占比过高", "情绪驱动交易较多。", f"冲动操作 {ratio:.1%}", "交易前记录理由并设置冷静期。", 7 if level == "red" else 4)
    no_plan = [t for t in recent30 if not t.get("plan_id") and not t.get("is_planned")]
    if len(no_plan) >= 3: add("no_plan", "交易行为风险", "yellow", "无计划交易过多", "多笔操作没有计划依据。", f"近 30 天 {len(no_plan)} 笔", "先建立计划，再执行交易。", 4)
    if cash < .05 and sum(bool(p.get("enabled", 1)) for p in plans) > 3: add("plans_no_cash", "交易行为风险", "yellow", "补仓计划多但现金不足", "计划可能超过资金承受力。", f"启用计划 {sum(bool(p.get('enabled', 1)) for p in plans)} 个", "为计划设置资金上限。", 4)
    directions = [str(t.get("action", "")) for t in recent7[:5]]
    if len(directions) >= 3 and len(set(directions[:3])) == 1 and directions[0] in {"买入", "补仓", "定投"}: add("same_direction", "交易行为风险", "yellow", "连续同方向加仓", "近期连续增加同类风险暴露。", f"最近连续 {directions[0]}", "暂停并重新检查组合总仓位。", 3)

    pending = [t for t in trades if t.get("review_status", "pending") == "pending" and t.get("review_date") and str(t["review_date"]) <= today.isoformat() and not t.get("review_result")]
    if len(pending) >= 5:
        level = "red" if len(pending) > 10 else "yellow"; add("pending_reviews", "复盘纪律风险", level, "到期未复盘过多", "复盘任务已经积压。", f"待复盘 {len(pending)} 条", "先完成复盘，再增加交易。", 7 if level == "red" else 4)
    completed = [t for t in trades if t.get("review_result")]
    if trades and len(completed)/len(trades) < .50: add("review_rate", "复盘纪律风险", "yellow", "复盘完成率低", "多数操作没有形成反馈闭环。", f"完成率 {len(completed)/len(trades):.1%}", "固定每周完成到期复盘。", 4)
    discipline = [safe_float(t.get("discipline_score")) for t in trades if t.get("discipline_score") is not None]
    confidence = [safe_float(t.get("confidence_score")) for t in trades if t.get("confidence_score") is not None]
    if discipline and sum(discipline)/len(discipline) < 6: add("discipline_low", "复盘纪律风险", "yellow", "纪律分偏低", "执行与计划偏差较多。", f"平均纪律分 {sum(discipline)/len(discipline):.1f}", "优先修正重复违反的纪律。", 3)
    if confidence and sum(confidence)/len(confidence) < 6: add("confidence_low", "复盘纪律风险", "yellow", "信心分偏低", "多次交易缺少充分依据。", f"平均信心分 {sum(confidence)/len(confidence):.1f}", "降低仓位并补充决策依据。", 2)
    tags = " ".join(str(t.get("mistake_tags", "")) for t in trades)
    for tag in ("追涨", "恐慌割肉", "无计划交易"):
        if tags.count(tag) >= 2: add(f"mistake_{tag}", "复盘纪律风险", "yellow", "常见错误重复出现", "同类错误标签较集中。", f"{tag} 出现 {tags.count(tag)} 次", "为该错误建立交易前检查项。", 3)

    missing_cost = int((frame["cost_amount"] <= 0).sum()); missing_type = int(frame["asset_type"].fillna("").isin(["", "其他"]).sum()); missing_risk = int(frame["risk_level"].fillna("").eq("").sum())
    if missing_cost: add("missing_cost", "数据质量风险", "yellow", "持仓缺少成本金额", "收益计算可能不准确。", f"缺少 {missing_cost} 条", "补齐成本金额后重新评估。", 3)
    if missing_type: add("missing_type", "数据质量风险", "yellow", "持仓缺少资产类型", "配置分析可能失真。", f"缺少或归为其他 {missing_type} 条", "补齐资产分类。", 2)
    if missing_risk: add("missing_risk", "数据质量风险", "yellow", "持仓缺少风险等级", "高风险资产比例无法准确计算。", f"缺少 {missing_risk} 条", "补齐风险等级。", 2)
    if sync_status and (not sync_status.get("sync_exists") or sync_status.get("possibly_out_of_sync") or sync_status.get("git_dirty")):
        add("sync_pending", "数据质量风险", "yellow", "本地数据尚未同步", "另一台设备可能不是最新数据。", "同步文件未导出或本地仍有改动", "完成导出并推送后再切换设备。", 3)
    market_data_provided = market_snapshots is not None or "snapshots" in kwargs
    snapshot_rows = list(market_snapshots or kwargs.get("snapshots") or ()); snapshot_ids = {row.get("holding_id") for row in snapshot_rows if row.get("holding_id")}
    if market_data_provided and records and len(snapshot_ids) / len(records) < .5:
        add("market_snapshot_incomplete", "数据质量风险", "yellow", "今日收益数据不完整", "风险判断可能缺少当日波动信息。", f"已更新 {len(snapshot_ids)}/{len(records)} 条", "可刷新市场快照或上传收益截图；无需据此进行交易。", 2)
    daily_pnl = sum(safe_float(row.get("daily_pnl")) for row in snapshot_rows)
    if market_data_provided and total and daily_pnl / total < -.02:
        add("large_daily_loss", "收益风险", "yellow", "单日波动较大", "今日收益快照显示组合波动偏大。", f"当日收益约占资产 {daily_pnl/total:.1%}", "注意情绪交易风险，先核对快照的数据来源和完整性。", 4)
    if not risks: add("portfolio_normal", "仓位风险", "green", "风险正常", "当前未触发主要风险规则。", "风险分 0", "保持记录并按计划复盘。", 0)
    return sorted(risks, key=lambda x: ({"red": 0, "yellow": 1, "green": 2}[x["level"]], -x["score"]))


def _date(value) -> date | None:
    try: return datetime.fromisoformat(str(value)).date()
    except (TypeError, ValueError): return None


def risk_summary(items: Iterable[Mapping]) -> dict:
    rows = list(items); dimensions = {}
    for category, limit in CATEGORY_WEIGHTS.items():
        dimensions[category] = min(limit, sum(int(r.get("score", 0)) for r in rows if r.get("category") == category))
    score = min(100, sum(dimensions.values())); level = "red" if score >= 61 else "yellow" if score >= 31 else "green"
    return {"risk_score": score, "level": level, "dimensions": dimensions,
            "red_count": sum(r.get("level") == "red" for r in rows), "yellow_count": sum(r.get("level") == "yellow" for r in rows), "green_count": sum(r.get("level") == "green" for r in rows)}


def system_suggestions(holdings: Iterable[Mapping], trades: Iterable[Mapping] = ()) -> list[str]:
    return [f"{item['icon']} {item['suggestion']}" for item in evaluate_risks(holdings, trades)[:5]]
