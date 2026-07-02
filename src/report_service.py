from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Iterable, Mapping

from src.calculations import enrich_holdings, portfolio_summary
from src.config import EXPORTS_DIR
from src.database import fetch_all
from src.review_service import get_review_summary
from src.rule_engine import evaluate_risks, risk_summary
from src.market_data_service import get_latest_market_snapshots

CHINESE_COLUMNS = {
    "name":"名称", "code":"代码", "platform":"平台", "asset_type":"资产类型", "market":"市场",
    "current_value":"当前市值", "cost_amount":"成本金额", "profit_amount":"浮盈亏", "profit_rate":"收益率",
    "holding_share":"持有份额", "latest_price":"最新价", "target_min_ratio":"目标下限", "target_max_ratio":"目标上限",
    "risk_level":"风险等级", "note":"备注", "trade_date":"操作日期", "asset_name":"资产名称", "action":"操作类型",
    "amount":"金额", "price":"价格", "reason":"操作原因", "emotion":"情绪", "review_date":"复盘日期",
    "review_result":"复盘结果", "status":"状态", "level":"风险等级", "title":"风险项", "description":"说明",
    "evidence":"依据", "suggestion":"建议", "score":"分数", "ratio":"占比", "target":"目标区间", "deviation":"偏离",
    "plan_type":"计划类型", "trigger_condition":"触发条件", "trigger_value":"触发值", "suggested_action":"建议动作", "priority":"优先级",
    "enabled":"是否启用", "quantity":"数量/份额", "confidence_score":"信心分", "discipline_score":"纪律分",
}


def default_market_snapshot(missing_count: int = 0) -> dict:
    return {"available":False,"source":"none","source_label":"暂无数据","total_daily_pnl":0.0,"matched_count":0,
            "missing_count":missing_count,"updated_at":None,"top_gainers":[],"top_losers":[],"top_daily_losses":[],
            "message":"暂无今日收益快照，可以刷新市场数据或上传第三方 App 收益截图。",
            "daily_pnl":0.0,"count":0,"sources":[],"largest_losses":[]}


def localize_records(records: Iterable[Mapping], columns: Iterable[str] | None = None) -> list[dict]:
    """Return user-facing records without database/debug fields and with Chinese headings."""
    hidden = {"id", "created_at", "updated_at", "raw_text", "parsed_json", "debug", "schema_version"}
    result = []
    for raw in records:
        keys = list(columns) if columns is not None else [key for key in raw if key not in hidden]
        row = {}
        for key in keys:
            value = raw.get(key)
            if key in {"current_value", "cost_amount", "profit_amount", "amount", "price"}:
                value = f"¥{float(value or 0):,.2f}"
            elif key in {"profit_rate", "target_min_ratio", "target_max_ratio", "ratio", "deviation"}:
                number = float(value or 0); value = f"{number:+.2%}" if key == "profit_rate" else f"{number:.2%}"
            row[CHINESE_COLUMNS.get(key, key)] = value
        result.append(row)
    return result


def generate_daily_report(holdings: Iterable[Mapping] | None = None, trades: Iterable[Mapping] | None = None,
                          plans: Iterable[Mapping] | None = None, settings: Mapping | None = None,
                          snapshots: Iterable[Mapping] | None = None) -> dict:
    holdings = list(fetch_all("holdings") if holdings is None else holdings)
    trades = list(fetch_all("trades", order_by="trade_date DESC") if trades is None else trades)
    plans = list(fetch_all("plans") if plans is None else plans)
    snapshots = list(get_latest_market_snapshots() if snapshots is None else snapshots)
    frame, overview = enrich_holdings(holdings), portfolio_summary(holdings)
    overview.update({"high_risk_ratio": float(frame.loc[frame.get("risk_level") == "高", "current_value"].sum() / max(frame["current_value"].sum(), 1)) if not frame.empty else 0,
                     "holding_count": len(holdings), "active_plan_count": sum(bool(p.get("enabled", 1)) for p in plans),
                     "pending_review_count": get_review_summary(trades)["pending_count"]})
    allocations = []
    if not frame.empty:
        total = max(float(frame["current_value"].sum()), 1)
        for kind, group in frame.groupby("asset_type"):
            amount, ratio = float(group["current_value"].sum()), float(group["current_value"].sum()/total)
            minimum, maximum = float(group["target_min_ratio"].min()), float(group["target_max_ratio"].max())
            status = "低配" if ratio < minimum else "超配" if ratio > maximum else "正常"
            deviation = minimum-ratio if status == "低配" else ratio-maximum if status == "超配" else 0
            allocations.append({"asset_type": kind, "amount": amount, "ratio": ratio, "target": f"{minimum:.0%}-{maximum:.0%}", "status": status, "deviation": deviation})
    platforms = frame.groupby("platform")["current_value"].sum().reset_index().to_dict("records") if not frame.empty else []
    risks = evaluate_risks(holdings, trades, settings, snapshots=snapshots)
    enabled_plans = sorted([p for p in plans if p.get("enabled", 1)], key=lambda p: p.get("priority", 9))
    due = [t for t in trades if t.get("review_status", "pending") == "pending" and t.get("review_date") and str(t["review_date"]) <= date.today().isoformat() and not t.get("review_result")]
    suggestions = [r["suggestion"] for r in risks if r["level"] != "green"][:5] or ["当前未触发主要风险规则，继续按计划记录和复盘。"]
    performance = [] if frame.empty else frame[["name", "profit_amount", "profit_rate"]].sort_values("profit_amount", ascending=False).to_dict("records")
    updated_ids = {row.get("holding_id") for row in snapshots if row.get("holding_id")}; market_snapshot = default_market_snapshot(max(0,len(holdings)-len(updated_ids)))
    if snapshots:
        sources=sorted({str(x.get("source")) for x in snapshots}); source="mixed" if len(sources)>1 else sources[0]
        label={"screenshot":"第三方截图","market_api":"API","manual":"手动录入","mixed":"混合"}.get(source,"其他")
        losses=sorted([dict(x) for x in snapshots if x.get("daily_pnl") is not None],key=lambda x:x.get("daily_pnl",0))[:3]
        market_snapshot.update({"available":True,"source":source,"source_label":label,"total_daily_pnl":sum(float(x.get("daily_pnl") or 0) for x in snapshots),
            "matched_count":len(updated_ids),"updated_at":max((str(x.get("fetched_at") or "") for x in snapshots),default=None),
            "top_gainers":sorted([dict(x) for x in snapshots if x.get("change_pct") is not None],key=lambda x:x.get("change_pct",0),reverse=True)[:3],
            "top_losers":sorted([dict(x) for x in snapshots if x.get("change_pct") is not None],key=lambda x:x.get("change_pct",0))[:3],
            "top_daily_losses":losses,"message":"今日收益快照仅供复盘参考，不代表官方最终净值。",
            "daily_pnl":sum(float(x.get("daily_pnl") or 0) for x in snapshots),"count":len(snapshots),"sources":sources,"largest_losses":losses})
    report = {"date": date.today().isoformat(), "overview": overview, "allocations": allocations, "platforms": platforms,
              "performance": performance, "risks": risks, "risk_summary": risk_summary(risks), "plans": enabled_plans,
              "pending_reviews": due, "suggestions": suggestions, "market_snapshot":market_snapshot}
    report["markdown"] = report_to_markdown(report)
    return report


def report_to_markdown(report: Mapping) -> str:
    o = report["overview"]
    lines = [f"# 投资日报 · {report['date']}", "", "## 今日总览",
             f"- 总资产：¥{o['total_asset']:,.2f}", f"- 总成本：¥{o['total_cost']:,.2f}",
             f"- 总浮盈亏：¥{o['total_profit']:,.2f}", f"- 总收益率：{o['profit_rate']:.2%}",
             f"- 现金比例：{o['cash_ratio']:.2%}", f"- 高风险资产比例：{o['high_risk_ratio']:.2%}",
             f"- 持仓 / 启用计划 / 待复盘：{o['holding_count']} / {o['active_plan_count']} / {o['pending_review_count']}",
             "", "## 资产配置摘要"]
    lines += [f"- {x['asset_type']}：¥{x['amount']:,.2f}（{x['ratio']:.2%}），目标 {x['target']}，{x['status']}" for x in report["allocations"]] or ["- 暂无持仓数据"]
    lines += ["", "## 风险提示"] + [f"- {x['icon']} {x['title']}：{x['evidence']}；建议：{x['suggestion']}" for x in report["risks"]]
    market = {**default_market_snapshot(), **(report.get("market_snapshot") or {})}
    lines += ["", "## 今日市场快照", f"- 今日收益合计：¥{float(market.get('total_daily_pnl') or 0):,.2f}", f"- 最新更新时间：{market.get('updated_at') or '暂无'}", f"- 数据来源：{market.get('source_label') or '暂无数据'}", f"- 未更新持仓：{market.get('missing_count', 0)}"]
    if market.get("top_gainers"): lines += ["- 涨幅居前：" + "、".join(f"{x.get('name','未命名')} {float(x.get('change_pct') or 0):+.2%}" for x in market["top_gainers"])]
    if market.get("top_losers"): lines += ["- 跌幅居前：" + "、".join(f"{x.get('name','未命名')} {float(x.get('change_pct') or 0):+.2%}" for x in market["top_losers"])]
    if market.get("top_daily_losses"): lines += ["- 当日亏损居前：" + "、".join(f"{x.get('name','未命名')} ¥{float(x.get('daily_pnl') or 0):+,.2f}" for x in market["top_daily_losses"])]
    if "screenshot" in market.get("sources", []): lines += ["- 今日收益来自第三方 App 截图，仅供复盘参考，不代表官方最终净值。"]
    elif market.get("count"): lines += ["- 数据来自可选市场接口；场外基金可能要等待净值更新。"]
    else: lines += [f"- {market.get('message')}"]
    lines += ["", "## 持仓收益", "", "| 名称 | 浮盈亏 | 收益率 |", "|---|---:|---:|"]
    lines += [f"| {x['name']} | ¥{x['profit_amount']:,.2f} | {x['profit_rate']:+.2%} |" for x in report["performance"]] or ["| 暂无持仓 | ¥0.00 | 0.00% |"]
    lines += ["", "## 买卖计划提醒"] + [f"- {x.get('asset_name')}：{x.get('trigger_condition') or '需要人工判断'} → {x.get('suggested_action') or '待填写'}" for x in report["plans"]] or ["- 暂无启用计划"]
    lines += ["", "## 复盘提醒"] + [f"- {x.get('trade_date')} {x.get('asset_name')} {x.get('action')}" for x in report["pending_reviews"]] or ["- 暂无到期未复盘操作"]
    lines += ["", "## 今日建议"] + [f"- {x}" for x in report["suggestions"]]
    lines += ["", "> 仅用于个人投资记录和辅助决策，不构成投资建议，不保证收益。"]
    return "\n".join(lines) + "\n"


def save_daily_report(report: Mapping, export_dir: Path = EXPORTS_DIR) -> Path:
    export_dir.mkdir(parents=True, exist_ok=True)
    path = export_dir / f"daily_report_{str(report.get('date', date.today().isoformat())).replace('-', '')}.md"
    path.write_text(str(report.get("markdown") or report_to_markdown(report)), encoding="utf-8")
    return path
