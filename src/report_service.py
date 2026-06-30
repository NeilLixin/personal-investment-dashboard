from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Iterable, Mapping

from src.calculations import enrich_holdings, portfolio_summary
from src.config import EXPORTS_DIR
from src.database import fetch_all
from src.review_service import get_review_summary
from src.rule_engine import evaluate_risks, risk_summary


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
