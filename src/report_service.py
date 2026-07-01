from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Iterable, Mapping

from src.calculations import enrich_holdings, portfolio_summary
from src.config import EXPORTS_DIR
from src.database import fetch_all
from src.review_service import get_review_summary
from src.rule_engine import evaluate_risks, risk_summary

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
                          plans: Iterable[Mapping] | None = None, settings: Mapping | None = None) -> dict:
    holdings = list(fetch_all("holdings") if holdings is None else holdings)
    trades = list(fetch_all("trades", order_by="trade_date DESC") if trades is None else trades)
    plans = list(fetch_all("plans") if plans is None else plans)
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
    risks = evaluate_risks(holdings, trades, settings)
    enabled_plans = sorted([p for p in plans if p.get("enabled", 1)], key=lambda p: p.get("priority", 9))
    due = [t for t in trades if t.get("review_status", "pending") == "pending" and t.get("review_date") and str(t["review_date"]) <= date.today().isoformat() and not t.get("review_result")]
    suggestions = [r["suggestion"] for r in risks if r["level"] != "green"][:5] or ["当前未触发主要风险规则，继续按计划记录和复盘。"]
    performance = [] if frame.empty else frame[["name", "profit_amount", "profit_rate"]].sort_values("profit_amount", ascending=False).to_dict("records")
    report = {"date": date.today().isoformat(), "overview": overview, "allocations": allocations, "platforms": platforms,
              "performance": performance, "risks": risks, "risk_summary": risk_summary(risks), "plans": enabled_plans,
              "pending_reviews": due, "suggestions": suggestions}
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
