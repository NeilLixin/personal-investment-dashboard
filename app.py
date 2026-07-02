from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.alipay_parser import parse_alipay_text
from src.alipay_fund_parser import parse_alipay_fund_holdings_from_ocr_items
from src.eastmoney_parser import parse_eastmoney_holdings_from_ocr_items
from src.calculations import allocation_status, apply_holding_operation, calculate_profit, enrich_holdings, format_currency, format_rate, portfolio_summary, safe_float
from src.config import (
    APP_VERSION, ASSET_TYPES, DATABASE_PATH, EMOTIONS, MARKETS, PLAN_TYPES, PLATFORMS,
    RISK_LEVELS, TRADE_ACTIONS, ensure_directories,
)
from src.database import (
    clear_tables, delete_row, fetch_all, get_row, get_setting, init_db, insert_row,
    now_text, set_setting, update_row,
)
from src.export_service import backup_database, export_all_csv_zip
from src.import_service import dedupe_import_holdings, import_holding_drafts, parsed_to_drafts, recommend_fund_codes_for_import
from src.fund_code_service import apply_confirmed_code_matches, batch_match_missing_holding_codes, load_fund_code_candidates, refresh_fund_code_candidates
from src.market_data_service import (
    get_latest_market_snapshots, get_market_refresh_status, merge_holdings_with_latest_snapshots,
    refresh_market_snapshots_for_holdings, save_market_snapshot,
)
from src.profit_screenshot_parser import (
    build_market_snapshot_from_profit_item, match_profit_items_to_holdings, parse_profit_screenshot_text, recommend_profit_item_codes,
)
from src.image_preprocess import (
    crop_alipay_fund_area,
    load_image_from_uploaded_file,
    preprocess_mobile_screenshot,
    save_ocr_debug_images,
    split_alipay_fund_rows,
)
from src.git_service import run_git_action
from src.ocr_engine import LocalOCREngine
from src.rule_engine import evaluate_risks, risk_summary, system_suggestions
from src.report_service import default_market_snapshot, generate_daily_report, localize_records, save_daily_report
from src.review_service import (
    generate_review_insights, get_emotion_stats, get_mistake_tag_stats,
    get_monthly_review_stats, get_review_summary, get_success_tag_stats,
)
from src.sync_service import export_sync_snapshot, get_sync_status, import_sync_snapshot
from src.sample_data import DEFAULT_ALLOCATION, seed_demo_data
from src.ui_components import PLOTLY_CONFIG, inject_css, metric_card, money_metric, page_header, rate_metric, risk_cards


st.set_page_config(page_title="个人投资驾驶舱", page_icon="🧭", layout="wide", initial_sidebar_state="expanded")
ensure_directories()
try:
    init_db()
except Exception as database_error:
    st.error("本地数据库升级失败。请先备份 data/investment_dashboard.db，再检查文件权限或迁移错误。")
    with st.expander("数据库升级诊断"):
        st.code(f"{type(database_error).__name__}: {database_error}")
    st.stop()
inject_css()


@st.cache_resource(show_spinner=False)
def get_local_ocr_engine() -> LocalOCREngine:
    """Initialize the optional OCR runtime once per Streamlit process."""
    return LocalOCREngine()


def rerun_with_message(message: str) -> None:
    st.session_state["flash_message"] = message
    st.rerun()


def show_flash() -> None:
    message = st.session_state.pop("flash_message", "")
    if message:
        st.success(message)


def holdings_data() -> tuple[list[dict], pd.DataFrame]:
    records = fetch_all("holdings")
    return records, enrich_holdings(records)


def market_snapshot_settings() -> dict:
    defaults = {"check_on_open":True, "auto_refresh":False, "min_interval_minutes":60, "api_source":"akshare",
                "screenshot_priority":True, "show_holding_columns":True, "show_in_report":True}
    return {**defaults, **(get_setting("market_snapshot_settings", {}) or {})}


def market_snapshot_summary(records: list[dict]) -> dict:
    settings = market_snapshot_settings(); snapshots = get_latest_market_snapshots(screenshot_priority=settings["screenshot_priority"])
    matched_ids = {row.get("holding_id") for row in snapshots if row.get("holding_id")}
    sources = {row.get("source") for row in snapshots}; source = "混合" if len(sources) > 1 else "第三方截图" if "screenshot" in sources else "API" if "market_api" in sources else "暂无"
    quality = {row.get("quality_level") for row in snapshots}
    quality_text = "部分缺失" if len(matched_ids) < len(records) else "第三方估算" if "third_party_estimate" in quality else "盘中行情" if "realtime_quote" in quality else "官方净值" if quality == {"official_nav"} else "部分缺失"
    latest = max((str(row.get("fetched_at") or "") for row in snapshots), default="")
    return {"snapshots":snapshots, "daily_pnl":sum(safe_float(row.get("daily_pnl")) for row in snapshots), "matched":len(matched_ids),
            "unmatched":max(0, len(records)-len(matched_ids)), "source":source, "quality":quality_text, "latest":latest}


def maybe_auto_refresh_market(records: list[dict]) -> None:
    settings = market_snapshot_settings()
    if not settings["check_on_open"]: return
    status = get_market_refresh_status(min_interval_minutes=int(settings["min_interval_minutes"]))
    marker = f"{date.today()}-{status.get('last_refreshed_at')}"
    if status["is_stale"] and settings["auto_refresh"] and st.session_state.get("market_auto_attempt") != marker:
        st.session_state["market_auto_attempt"] = marker
        st.session_state["market_refresh_result"] = refresh_market_snapshots_for_holdings(records)


def save_holding(payload: dict, holding_id: int | None = None) -> None:
    profit, rate = calculate_profit(payload["current_value"], payload["cost_amount"], payload.get("profit_amount"))
    payload["profit_amount"] = profit
    payload["profit_rate"] = rate
    if holding_id:
        update_row("holdings", holding_id, payload)
    else:
        insert_row("holdings", payload)


def dashboard_page() -> None:
    page_header("🧭 个人投资驾驶舱", "看清配置、约束仓位、按计划行动；不预测市场，也不自动交易。")
    records, frame = holdings_data()
    trades = fetch_all("trades", order_by="trade_date DESC, id DESC")
    summary = portfolio_summary(records)
    maybe_auto_refresh_market(records)
    market = market_snapshot_summary(records)
    due_reviews = [row for row in trades if row.get("review_date") and row["review_date"] <= date.today().isoformat() and not (row.get("review_result") or "").strip()]
    over_count = int((frame.get("allocation_status", pd.Series(dtype=str)) == "超配").sum()) if not frame.empty else 0
    under_count = int((frame.get("allocation_status", pd.Series(dtype=str)) == "低配").sum()) if not frame.empty else 0
    cards = st.columns(4)
    with cards[0]: money_metric("总资产", summary["total_asset"])
    with cards[1]: money_metric("总成本", summary["total_cost"])
    with cards[2]: money_metric("总浮盈亏", summary["total_profit"], signed=True)
    with cards[3]: rate_metric("总收益率", summary["profit_rate"], signed=True)
    cards = st.columns(4)
    with cards[0]: rate_metric("现金比例", summary["cash_ratio"])
    with cards[1]: metric_card("今日待复盘", str(len(due_reviews)))
    with cards[2]: metric_card("超配 / 低配", f"{over_count} / {under_count}")
    with cards[3]: metric_card("持仓数量", str(len(records)))
    st.subheader("今日收益快照")
    mc = st.columns(5)
    with mc[0]: money_metric("今日收益合计", market["daily_pnl"], signed=True)
    with mc[1]: metric_card("已更新持仓", str(market["matched"]))
    with mc[2]: metric_card("待更新持仓", str(market["unmatched"]))
    with mc[3]: metric_card("数据来源", market["source"])
    with mc[4]: metric_card("数据质量", market["quality"])
    refresh_status = get_market_refresh_status(min_interval_minutes=int(market_snapshot_settings()["min_interval_minutes"]))
    if refresh_status["is_stale"]: st.warning("市场快照已超过 1 小时未更新。自动市场数据不可用时，可上传第三方 App 收益截图更新。")
    elif refresh_status["minutes_since_refresh"] is not None: st.caption(f"上次 API 更新：{refresh_status['minutes_since_refresh']:.0f} 分钟前")
    if "screenshot" in {row.get("source") for row in market["snapshots"]}: st.caption("今日收益快照来自第三方截图，仅用于复盘参考，不代表官方最终净值。")
    if st.button("刷新市场快照", help="频繁刷新可能被数据源限制。", key="dashboard_market_refresh"):
        st.session_state["market_refresh_result"] = refresh_market_snapshots_for_holdings(records, force=True); st.rerun()
    if st.session_state.get("market_refresh_result"):
        result = st.session_state["market_refresh_result"]
        st.caption(f"刷新结果：成功 {result.get('success_count',0)}，失败 {result.get('failed_count',0)}，跳过 {result.get('skipped_count',0)}。")
        if not result.get("success_count"):
            st.warning(result.get("error") or result.get("message") or "本次没有成功更新，查看高级诊断了解原因。")
        with st.expander("市场刷新高级诊断"):
            st.write("数据源状态", result.get("provider"))
            st.write("失败项目", result.get("failed_items", []))
            st.write("跳过项目", result.get("skipped_items", []))
            st.write("最近刷新日志", fetch_all("market_refresh_logs")[:5])
            if result.get("error"): st.code(str(result["error"]))
    if frame.empty:
        st.info("暂无持仓。可以先到“数据备份/设置”初始化 demo 数据，或前往“持仓管理”录入。")
        return
    left, right = st.columns(2)
    with left:
        allocation = frame.groupby("asset_type", as_index=False)["current_value"].sum()
        fig = px.pie(allocation, names="asset_type", values="current_value", hole=.55, title="资产类型配置", labels={"asset_type":"资产类型", "current_value":"当前市值"})
        st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG)
        targets = get_setting("target_allocations", DEFAULT_ALLOCATION); total = max(float(frame["current_value"].sum()), 1)
        allocation["当前占比"] = allocation["current_value"] / total
        allocation["目标区间"] = allocation["asset_type"].map(lambda x:f"{targets.get(x, {'min':0,'max':1})['min']:.0%}-{targets.get(x, {'min':0,'max':1})['max']:.0%}")
        allocation["配置状态"] = allocation.apply(lambda x: allocation_status(x["当前占比"], targets.get(x["asset_type"], {"min":0})["min"], targets.get(x["asset_type"], {"max":1})["max"]), axis=1)
        st.dataframe(allocation[["asset_type", "当前占比", "目标区间", "配置状态"]].rename(columns={"asset_type":"资产类型"}), hide_index=True, width="stretch", column_config={"当前占比":st.column_config.NumberColumn(format="%.2%%")})
    with right:
        platforms = frame.groupby("platform", as_index=False)["current_value"].sum()
        fig = px.bar(platforms, x="platform", y="current_value", color="platform", title="平台资产分布", labels={"platform":"平台", "current_value":"当前市值"})
        fig.update_layout(showlegend=False, yaxis_title="当前市值")
        st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG)
    left, right = st.columns([1.3, 1])
    with left:
        profit_frame = frame.sort_values("profit_amount")
        fig = px.bar(profit_frame, x="profit_amount", y="name", orientation="h", color="profit_amount",
                     color_continuous_scale=["#c43d3d", "#f0f2f5", "#0f8a5f"], title="持仓浮盈亏排序")
        st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG)
    with right:
        st.subheader("风险雷达")
        risk_cards(evaluate_risks(records, trades)[:4])
    st.subheader("今日系统建议")
    for suggestion in system_suggestions(records, trades):
        st.write(suggestion)


def holding_form(prefix: str, initial: dict | None = None) -> dict | None:
    initial = initial or {}
    with st.form(f"{prefix}_form"):
        c1, c2, c3 = st.columns(3)
        name = c1.text_input("名称 *", value=str(initial.get("name", "")))
        code = c2.text_input("代码", value=str(initial.get("code") or ""))
        platform = c3.selectbox("平台", PLATFORMS, index=PLATFORMS.index(initial.get("platform")) if initial.get("platform") in PLATFORMS else 0)
        c1, c2, c3 = st.columns(3)
        asset_type = c1.selectbox("资产类型", ASSET_TYPES, index=ASSET_TYPES.index(initial.get("asset_type")) if initial.get("asset_type") in ASSET_TYPES else 0)
        market = c2.selectbox("市场", MARKETS, index=MARKETS.index(initial.get("market")) if initial.get("market") in MARKETS else 0)
        risk = c3.selectbox("风险等级", RISK_LEVELS, index=RISK_LEVELS.index(initial.get("risk_level")) if initial.get("risk_level") in RISK_LEVELS else 1)
        c1, c2, c3 = st.columns(3)
        current = c1.number_input("当前市值", min_value=0.0, value=safe_float(initial.get("current_value")), step=100.0)
        cost = c2.number_input("成本金额", min_value=0.0, value=safe_float(initial.get("cost_amount")), step=100.0)
        profit_default = initial.get("profit_amount")
        profit = c3.number_input("浮盈亏（留 0 可按市值-成本计算）", value=safe_float(profit_default), step=100.0)
        c1, c2, c3, c4 = st.columns(4)
        share = c1.number_input("持有份额", min_value=0.0, value=safe_float(initial.get("holding_share")), step=.01)
        price = c2.number_input("最新净值/价格", min_value=0.0, value=safe_float(initial.get("latest_price")), step=.0001, format="%.4f")
        minimum = c3.number_input("目标最低占比 %", min_value=0.0, max_value=100.0, value=safe_float(initial.get("target_min_ratio")) * 100, step=1.0)
        maximum = c4.number_input("目标最高占比 %", min_value=0.0, max_value=100.0, value=safe_float(initial.get("target_max_ratio"), 1.0) * 100, step=1.0)
        note = st.text_area("备注", value=str(initial.get("note") or ""))
        submitted = st.form_submit_button("保存持仓", type="primary", width="stretch")
    if not submitted:
        return None
    if not name.strip():
        st.error("名称不能为空。")
        return None
    return {"name": name.strip(), "code": code.strip(), "platform": platform, "asset_type": asset_type, "market": market,
            "current_value": current, "cost_amount": cost, "profit_amount": profit if profit else None,
            "holding_share": share or None, "latest_price": price or None, "target_min_ratio": minimum / 100,
            "target_max_ratio": maximum / 100, "risk_level": risk, "note": note.strip()}


def holdings_page() -> None:
    page_header("📦 持仓工作台", "查看组合、记录操作、管理计划和调整持仓设置。")
    show_flash()
    records, frame = holdings_data()
    merged_snapshots = merge_holdings_with_latest_snapshots(records)
    snapshot_columns = [column for column in merged_snapshots.columns if column.startswith("snapshot_")]
    if not frame.empty and snapshot_columns:
        frame = frame.merge(merged_snapshots[["id", *snapshot_columns]], on="id", how="left")
    trades = fetch_all("trades", order_by="trade_date DESC, id DESC")
    summary = portfolio_summary(records); risks = evaluate_risks(records, trades)
    pending = [row for row in trades if row.get("review_status", "pending") == "pending" and not row.get("review_result")]
    cards = st.columns(7)
    values = [format_currency(summary["total_asset"]), format_currency(summary["total_profit"], True), format_rate(summary["profit_rate"], True),
              format_rate(summary["cash_ratio"]), str(len(records)), str(sum(r["level"] == "red" for r in risks)), str(len(pending))]
    for col, label, value in zip(cards, ["总资产", "总浮盈亏", "总收益率", "现金比例", "持仓数量", "红色风险", "待复盘"], values):
        with col: metric_card(label, value)
    missing_codes = [row for row in records if not str(row.get("code") or "").strip()]
    with st.expander("🔎 基金代码补全助手", expanded=bool(missing_codes)):
        candidates = load_fund_code_candidates()
        latest = max((str(row.get("updated_at") or "") for row in candidates), default="尚未刷新")
        st.caption(f"持仓 {len(records)} 条 · 缺少代码 {len(missing_codes)} 条 · 候选 {len(candidates)} 条 · 最近更新 {latest}")
        st.info("代码只会在确认后写入；名称截断、A/C 类别不明确或多个近似候选不会自动勾选。")
        refresh_col, match_col = st.columns(2)
        if refresh_col.button("刷新基金代码候选库", width="stretch", key="refresh_fund_candidates"):
            with st.spinner("正在从 AKShare 更新基金候选库……"): result = refresh_fund_code_candidates(force=True)
            if result["ok"]: st.success(f"候选库已更新，共 {result['total']} 条。")
            else: st.error("候选库刷新失败：" + "；".join(result.get("errors") or ["未知错误"]))
        if match_col.button("自动匹配缺失代码", disabled=not missing_codes, width="stretch", key="match_missing_codes"):
            st.session_state["fund_code_matches"] = batch_match_missing_holding_codes(records)
        batch = st.session_state.get("fund_code_matches")
        if batch:
            st.write(f"完全匹配 {batch['exact_count']} · 高置信 {batch['high_confidence_count']} · 多候选 {batch['multiple_count']} · 低置信 {batch['low_confidence_count']} · 未匹配 {batch['no_match_count']}")
            rows = [{"是否写入":item["default_selected"], "持仓ID":item["holding_id"], "平台":item.get("platform"), "本地持仓名称":item["holding_name"], "当前代码":item.get("current_code", ""),
                "推荐代码":item["recommended_code"], "推荐名称":item["recommended_name"], "基金类型":item.get("fund_type"), "置信度":item["confidence"],
                "匹配状态":item["status"], "其他候选":"；".join(f"{x['code']} {x['name']} ({x['confidence']:.0%})" for x in item.get("candidates", [])[:3]), "匹配原因":item["reason"], "备注":"请人工确认"}
                for item in batch["items"]]
            edited_codes = st.data_editor(pd.DataFrame(rows), hide_index=True, width="stretch", key="fund_code_editor",
                disabled=["持仓ID","平台","本地持仓名称","当前代码","推荐名称","基金类型","置信度","匹配状态","其他候选","匹配原因"], column_config={"置信度":st.column_config.NumberColumn(format="%.0%%")})
            if st.button("保存已确认代码", type="primary", key="save_confirmed_codes"):
                confirmations = [{"confirmed":row["是否写入"], "holding_id":row["持仓ID"], "recommended_code":row["推荐代码"], "holding_name":row["本地持仓名称"],
                    "recommended_name":row["推荐名称"], "confidence":row["置信度"], "status":row["匹配状态"]} for row in edited_codes.to_dict("records")]
                saved = apply_confirmed_code_matches(confirmations)
                rerun_with_message(f"基金代码补全完成：写入 {saved['updated']}，跳过 {saved['skipped']}，冲突 {saved['conflicts']}，失败 {saved['failed']}。")
    with st.expander("➕ 新增持仓", expanded=not records):
        payload = holding_form("add_holding")
        if payload:
            save_holding(payload)
            rerun_with_message("持仓已新增。")
    with st.expander("📥 导入 CSV / 导出 CSV"):
        uploaded = st.file_uploader("导入 holdings CSV", type=["csv"], key="holding_csv")
        if uploaded:
            imported = pd.read_csv(uploaded).fillna("")
            st.dataframe(imported.head(20), width="stretch")
            if st.button("确认导入 CSV", type="primary"):
                result = import_holding_drafts(imported.to_dict("records"))
                rerun_with_message(f"CSV 导入完成：新增 {result['inserted']}，更新 {result['updated']}，跳过 {result['skipped']}。")
        if not frame.empty:
            st.download_button("下载当前持仓 CSV", frame.to_csv(index=False).encode("utf-8-sig"), "holdings.csv", "text/csv")
    if frame.empty:
        st.info("暂无持仓，请先手动新增或上传截图导入。")
        return
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    platform_filter = c1.multiselect("平台筛选", sorted(frame["platform"].dropna().unique()))
    type_filter = c2.multiselect("资产类型筛选", sorted(frame["asset_type"].dropna().unique()))
    risk_filter = c3.multiselect("风险等级", RISK_LEVELS)
    profit_filter = c4.selectbox("盈亏状态", ["全部", "盈利", "亏损", "持平"])
    sort_key = c5.selectbox("排序", ["当前市值", "浮盈亏", "收益率", "持仓占比"])
    snapshot_filter = c6.selectbox("今日快照", ["全部", "今日上涨", "今日下跌", "未更新", "第三方截图", "API"])
    display = frame.copy()
    if platform_filter: display = display[display["platform"].isin(platform_filter)]
    if type_filter: display = display[display["asset_type"].isin(type_filter)]
    if risk_filter: display = display[display["risk_level"].isin(risk_filter)]
    if profit_filter != "全部": display = display[(display["profit_amount"] > 0) if profit_filter == "盈利" else (display["profit_amount"] < 0) if profit_filter == "亏损" else (display["profit_amount"] == 0)]
    if snapshot_filter == "今日上涨": display = display[display.get("snapshot_change_pct", pd.Series(index=display.index, dtype=float)).fillna(0) > 0]
    elif snapshot_filter == "今日下跌": display = display[display.get("snapshot_change_pct", pd.Series(index=display.index, dtype=float)).fillna(0) < 0]
    elif snapshot_filter == "未更新": display = display[display.get("snapshot_fetched_at", pd.Series(index=display.index, dtype=object)).isna()]
    elif snapshot_filter == "第三方截图": display = display[display.get("snapshot_source", pd.Series(index=display.index, dtype=object)) == "screenshot"]
    elif snapshot_filter == "API": display = display[display.get("snapshot_source", pd.Series(index=display.index, dtype=object)) == "market_api"]
    display = display.sort_values({"当前市值":"current_value", "浮盈亏":"profit_amount", "收益率":"profit_rate", "持仓占比":"asset_ratio"}[sort_key], ascending=False)
    category_tabs = st.tabs(["全部持仓", "A股", "海外", "黄金", "现金/固收", "高风险"])
    tab_frames = [display, display[display["market"] == "A股"], display[display["asset_type"] == "海外资产"], display[display["asset_type"] == "黄金"],
                  display[display["asset_type"].isin(["现金", "债券/固收"])], display[display["risk_level"] == "高"]]
    for tab, tab_frame in zip(category_tabs, tab_frames):
        with tab:
            if tab_frame.empty: st.info("当前分类暂无持仓。")
            else:
                shown = tab_frame[["name", "platform", "asset_type", "current_value", "cost_amount", "profit_amount", "profit_rate", "holding_share", "latest_price", "asset_ratio", "risk_level", "display_status", "allocation_status"]].copy()
                shown.columns = ["名称", "平台", "资产类型", "当前市值", "成本金额", "浮盈亏", "收益率", "持有份额", "最新价", "持仓占比", "风险等级", "状态", "配置状态"]
                shown.insert(7, "昨日/今日收益", tab_frame.get("daily_profit"))
                if market_snapshot_settings()["show_holding_columns"]:
                    shown["今日涨跌幅"] = tab_frame.get("snapshot_change_pct")
                    shown["今日收益"] = tab_frame.get("snapshot_daily_pnl")
                    shown["最新值"] = tab_frame.get("snapshot_latest_value")
                    shown["快照时间"] = tab_frame.get("snapshot_fetched_at")
                    shown["快照来源"] = tab_frame.get("snapshot_source").map({"screenshot":"第三方截图", "market_api":"API", "manual":"手动"}) if "snapshot_source" in tab_frame else None
                    shown["数据状态"] = tab_frame.get("snapshot_status")
                shown["操作"] = "在下方选择持仓"
                st.dataframe(shown, width="stretch", hide_index=True, column_config={"当前市值":st.column_config.NumberColumn(format="¥%.2f"), "成本金额":st.column_config.NumberColumn(format="¥%.2f"), "浮盈亏":st.column_config.NumberColumn(format="%+.2f"), "收益率":st.column_config.NumberColumn(format="%+.2%%"), "持仓占比":st.column_config.NumberColumn(format="%.2%%"), "今日涨跌幅":st.column_config.NumberColumn(format="%+.2%%"), "今日收益":st.column_config.NumberColumn(format="%+.2f")})
    st.subheader("持仓详情")
    choices = {f"#{row['id']} {row['name']}": int(row["id"]) for row in records}
    selected_label = st.selectbox("选择要操作的持仓", list(choices))
    selected_id = choices[selected_label]
    initial = get_row("holdings", selected_id)
    snapshot_tab, quick_tab, plan_tab, trade_tab, review_tab, setting_tab = st.tabs(["今日收益快照", "快速操作", "买卖计划", "操作记录", "复盘记录", "持仓设置"])
    with snapshot_tab:
        snapshot = next((row for row in get_latest_market_snapshots() if row.get("holding_id") == selected_id), None)
        if snapshot:
            sc = st.columns(5)
            with sc[0]: rate_metric("今日涨跌幅", safe_float(snapshot.get("change_pct")), signed=True)
            with sc[1]: money_metric("今日收益", safe_float(snapshot.get("daily_pnl")), signed=True)
            with sc[2]: money_metric("持有收益", safe_float(snapshot.get("holding_pnl")), signed=True)
            with sc[3]: metric_card("数据来源", "第三方截图" if snapshot.get("source") == "screenshot" else "API" if snapshot.get("source") == "market_api" else "手动")
            with sc[4]: metric_card("更新时间", str(snapshot.get("fetched_at") or ""))
            st.caption("场外基金净值通常不是盘中实时官方数据；第三方估算仅供复盘参考。")
            with st.expander("高级信息"): st.write({"快照记录":snapshot.get("id"), "来源":snapshot.get("source_name"), "状态":snapshot.get("status")})
        else:
            st.info("暂无今日收益快照，可以刷新市场数据或上传第三方 App 收益截图。")
    with quick_tab:
        with st.form(f"quick_operation_{selected_id}"):
            c1, c2, c3, c4 = st.columns(4); action = c1.selectbox("操作类型", TRADE_ACTIONS); amount = c2.number_input("金额", min_value=0.0); quantity = c3.number_input("数量/份额", min_value=0.0); price = c4.number_input("价格", min_value=0.0, format="%.4f")
            reason = st.text_area("操作原因"); c1, c2, c3 = st.columns(3); emotion = c1.selectbox("情绪", EMOTIONS); planned = c2.checkbox("是否按计划"); review_date = c3.date_input("复盘日期", date.today()); note = st.text_input("备注")
            c1, c2 = st.columns(2); record_only = c1.form_submit_button("仅记录操作", type="primary", width="stretch"); record_update = c2.form_submit_button("记录并更新持仓", width="stretch")
        if record_only or record_update:
            insert_row("trades", {"trade_date":date.today().isoformat(), "asset_name":initial["name"], "action":action, "amount":amount, "quantity":quantity or None,
                "price":price or None, "reason":reason, "emotion":emotion, "is_planned":int(planned), "review_date":review_date.isoformat(), "review_status":"pending", "note":note})
            if record_update and action != "观察":
                changed = apply_holding_operation(initial, action, amount, quantity, price)
                update_row("holdings", selected_id, {key:changed.get(key) for key in ("current_value", "cost_amount", "profit_amount", "profit_rate", "holding_share", "latest_price")})
            rerun_with_message("操作已记录" + ("，持仓已更新。" if record_update and action != "观察" else "。"))
    with plan_tab:
        related = [p for p in fetch_all("plans") if p.get("asset_name") == initial["name"]]
        if related: st.dataframe(pd.DataFrame(localize_records(related, ["plan_type", "trigger_condition", "trigger_value", "suggested_action", "priority", "enabled", "note"])), hide_index=True, width="stretch")
        else: st.info("当前持仓暂无买卖计划。")
        with st.form(f"holding_plan_{selected_id}"):
            c1, c2, c3 = st.columns(3); kind = c1.selectbox("计划类型", PLAN_TYPES); trigger = c2.number_input("触发值"); priority = c3.selectbox("优先级", [1,2,3], format_func=lambda x:{1:"高",2:"中",3:"低"}[x]); condition = st.text_input("条件"); suggestion = st.text_input("建议动作"); enabled = st.checkbox("是否启用", True); plan_note = st.text_input("计划备注")
            if st.form_submit_button("新增计划"):
                insert_row("plans", {"asset_name":initial["name"], "plan_type":kind, "trigger_condition":condition, "trigger_value":trigger, "suggested_action":suggestion, "priority":priority, "enabled":int(enabled), "note":plan_note}); rerun_with_message("计划已新增。")
    related_trades = [t for t in trades if t.get("asset_name") == initial["name"]]
    with trade_tab:
        if related_trades:
            action_filter = st.multiselect("筛选操作类型", TRADE_ACTIONS, key=f"trade_filter_{selected_id}")
            filtered_trades = [row for row in related_trades if not action_filter or row.get("action") in action_filter]
            st.dataframe(pd.DataFrame(localize_records(filtered_trades, ["trade_date", "action", "amount", "quantity", "price", "reason", "emotion", "review_date", "note"])), hide_index=True, width="stretch")
            trade_to_edit = st.selectbox("选择要编辑的记录", related_trades, format_func=lambda x:f"{x['trade_date']} · {x['action']} · {format_currency(x.get('amount', 0))}")
            with st.expander("编辑所选操作记录"):
                with st.form(f"edit_trade_{trade_to_edit['id']}"):
                    edit_action = st.selectbox("操作类型", TRADE_ACTIONS, index=TRADE_ACTIONS.index(trade_to_edit["action"]) if trade_to_edit.get("action") in TRADE_ACTIONS else 0)
                    edit_amount = st.number_input("金额", min_value=0.0, value=safe_float(trade_to_edit.get("amount")))
                    edit_reason = st.text_area("操作原因", trade_to_edit.get("reason") or "")
                    edit_emotion = st.selectbox("情绪", EMOTIONS, index=EMOTIONS.index(trade_to_edit["emotion"]) if trade_to_edit.get("emotion") in EMOTIONS else 0)
                    if st.form_submit_button("保存操作记录"):
                        update_row("trades", trade_to_edit["id"], {"action":edit_action, "amount":edit_amount, "reason":edit_reason, "emotion":edit_emotion}); rerun_with_message("操作记录已更新。")
        else: st.info("暂无操作记录。")
    with review_tab:
        reviewed = [t for t in related_trades if t.get("review_result")]
        if reviewed: st.dataframe(pd.DataFrame(localize_records(reviewed, ["trade_date", "action", "amount", "review_date", "review_result", "discipline_score"])), hide_index=True, width="stretch")
        else: st.info("暂无复盘记录。")
        pending_related = [t for t in related_trades if not t.get("review_result")]
        if pending_related:
            target = st.selectbox("选择待复盘操作", pending_related, format_func=lambda x:f"{x['trade_date']} · {x['action']}")
            with st.form(f"holding_review_{target['id']}"):
                result_text = st.text_area("复盘结果")
                if st.form_submit_button("保存复盘"):
                    update_row("trades", target["id"], {"review_result":result_text, "review_status":"done"}); rerun_with_message("复盘已保存。")
    with setting_tab:
        payload = holding_form(f"edit_holding_{selected_id}", initial)
        if payload: save_holding(payload, selected_id); rerun_with_message("持仓设置已更新。")
        if st.button("删除所选持仓", type="secondary"): delete_row("holdings", selected_id); rerun_with_message("持仓已删除。")


def holdings_screenshot_import_panel() -> None:
    advanced = st.toggle("高级调试模式", value=False)
    engine = get_local_ocr_engine()
    status = engine.status
    if not status.available:
        st.error("本地 OCR 未安装，请执行 pip install -r requirements-ocr.txt，安装后重启项目。")
    enable_preprocess, save_debug = True, False
    manual_type = "自动判断"
    if advanced:
        c1, c2, c3 = st.columns(3)
        with c1: metric_card("OCR 引擎", status.engine)
        with c2: metric_card("OCR 状态", "可用" if status.available else "不可用")
        with c3: metric_card("识别方式", "本机离线")
        manual_type = st.selectbox("截图类型", ["自动判断", "支付宝基金", "东方财富", "普通 OCR 文本"])
        enable_preprocess = st.toggle("启用图片预处理", value=True)
        save_debug = st.toggle("保存 OCR 调试图片", value=False)
    files = st.file_uploader("上传持仓截图（可多选）", type=["png", "jpg", "jpeg", "webp"], accept_multiple_files=True)
    prepared_files: list[dict] = []
    if files:
        st.markdown(f"已上传 {len(files)} 张图片，系统将自动识别。")
        for index, file in enumerate(files):
            try:
                original = load_image_from_uploaded_file(file)
                cropped = crop_alipay_fund_area(original) if enable_preprocess else original
                processed = preprocess_mobile_screenshot(cropped) if enable_preprocess else cropped
                prepared_files.append({"name": file.name, "original": original, "processed": processed})
            except Exception as exc:
                st.error(f"{file.name} 无法读取，请换一张清晰截图。")

    def detect_type(text: str) -> str:
        compact = text.replace(" ", "")
        alipay = sum(key in compact for key in ("支付宝", "基金", "我的持有", "金额/昨日收益", "持有收益/率"))
        eastmoney = sum(key in compact for key in ("东方财富", "普通", "总资产", "证券市值", "持仓盈亏", "场内基金", "现价", "成本"))
        return "支付宝基金" if alipay >= 2 else "东方财富" if eastmoney >= 2 else "未知"

    def run_ocr() -> None:
        with st.spinner("正在识别并解析持仓……"):
            results, parsed, errors, debug = [], [], [], []
            for prepared in prepared_files:
                if save_debug:
                    save_ocr_debug_images([prepared["processed"]], prepared["name"])
                result = engine.recognize_image(prepared["processed"]); result["name"] = prepared["name"]; results.append(result)
                if not result["ok"]:
                    errors.append(prepared["name"]); continue
                screenshot_type = manual_type if manual_type != "自动判断" else detect_type(result.get("text", ""))
                size = result.get("details", {}).get("processed_size") or prepared["processed"].size
                if screenshot_type == "支付宝基金":
                    parsed_result = parse_alipay_fund_holdings_from_ocr_items(result.get("items"), size[0], size[1])
                elif screenshot_type == "东方财富":
                    parsed_result = parse_eastmoney_holdings_from_ocr_items(result.get("items"), size[0], size[1])
                else:
                    parsed_result = {"ok": False, "holdings": [], "debug": {"reason": "无法自动判断截图类型"}, "error": "无法判断截图类型"}
                parsed.extend(parsed_result["holdings"]); debug.append({"文件": prepared["name"], "类型": screenshot_type, **parsed_result})
            unique_rows, duplicate_count = dedupe_import_holdings(parsed)
            st.session_state["ocr_results"] = {"results": results, "errors": errors, "debug": debug}
            st.session_state["ocr_drafts"] = parsed_to_drafts(unique_rows)
            st.session_state["ocr_duplicate_count"] = duplicate_count
            st.session_state["ocr_parse_failed"] = not bool(unique_rows)
        if parsed:
            st.success(f"识别完成，共解析出 {len(unique_rows)} 条持仓，请确认后导入。")
            if duplicate_count: st.warning("本次导入发现重复持仓，已默认使用最后一次识别结果。")
        elif results and any(item.get("ok") for item in results):
            st.warning("已识别到文字，但没有解析出完整持仓。请打开高级调试模式查看原因。")
        else:
            st.error("截图识别失败，请确认图片清晰后重新识别。")

    signature = tuple((file.name, getattr(file, "size", len(file.getvalue()))) for file in (files or []))
    if prepared_files and status.available and st.session_state.get("ocr_auto_signature") != (signature, manual_type, enable_preprocess):
        st.session_state["ocr_auto_signature"] = (signature, manual_type, enable_preprocess)
        run_ocr()
    c1, c2 = st.columns(2)
    if c1.button("重新识别", disabled=not prepared_files, width="stretch"):
        run_ocr()
    if c2.button("清空本次结果", width="stretch"):
        for key in ("ocr_results", "ocr_drafts", "ocr_auto_signature", "ocr_parse_failed"):
            st.session_state.pop(key, None)
        st.rerun()
    ocr_result = st.session_state.get("ocr_results", {})
    if advanced and ocr_result:
        with st.expander("OCR 与解析调试信息", expanded=True):
            for prepared in prepared_files: st.image(prepared["processed"], caption=f"预处理图 · {prepared['name']}")
            for result in ocr_result.get("results", []):
                st.text_area(f"OCR 原文 · {result.get('name')}", result.get("text", ""), disabled=True)
                st.dataframe(pd.DataFrame(result.get("items", [])), hide_index=True, width="stretch")
            st.json(ocr_result.get("debug", []))
        manual_text = st.text_area("手动粘贴 OCR 文本（fallback）")
        if manual_text and st.button("按普通文本解析"):
            st.session_state["ocr_drafts"] = parsed_to_drafts(parse_alipay_text(manual_text))
    drafts = st.session_state.get("ocr_drafts")
    if isinstance(drafts, pd.DataFrame) and not drafts.empty:
        recommended = recommend_fund_codes_for_import(drafts.to_dict("records"), load_fund_code_candidates())
        drafts = pd.DataFrame(recommended)
        if st.session_state.get("ocr_duplicate_count"): st.warning("本次导入发现重复持仓，已默认使用最后一次识别结果。")
        st.subheader("待确认导入表格")
        display = drafts.rename(columns={"name":"名称", "code":"代码", "recommended_code":"推荐基金代码", "recommended_name":"推荐基金名称", "code_match_status":"代码匹配状态", "write_recommended_code":"是否写入代码", "platform":"平台", "asset_type":"资产类型", "market":"市场",
            "current_value":"当前市值", "cost_amount":"成本金额", "profit_amount":"浮盈亏", "profit_rate":"收益率",
            "yesterday_profit":"昨日/今日收益", "holding_share":"份额", "latest_price":"最新价", "risk_level":"风险等级",
            "note":"备注", "duplicate_action":"导入策略"})
        display.insert(0, "选择", True)
        visible = ["选择", "名称", "代码", "推荐基金代码", "推荐基金名称", "代码匹配状态", "是否写入代码", "平台", "资产类型", "市场", "当前市值", "成本金额", "浮盈亏", "收益率", "昨日/今日收益", "份额", "最新价", "风险等级", "备注", "导入策略"]
        edited = st.data_editor(
            display[visible], width="stretch", num_rows="dynamic", key="ocr_editor",
            column_config={
                "平台": st.column_config.SelectboxColumn(options=PLATFORMS), "资产类型": st.column_config.SelectboxColumn(options=ASSET_TYPES),
                "市场": st.column_config.SelectboxColumn(options=MARKETS), "风险等级": st.column_config.SelectboxColumn(options=RISK_LEVELS),
                "导入策略": st.column_config.SelectboxColumn(options=["覆盖更新", "新增一条", "跳过"]),
                "当前市值": st.column_config.NumberColumn(format="¥%.2f"), "成本金额": st.column_config.NumberColumn(format="¥%.2f"),
                "浮盈亏": st.column_config.NumberColumn(format="%+.2f"), "收益率": st.column_config.NumberColumn(format="%+.2%%"),
            },
        )
        if st.button("确认导入选中持仓", type="primary"):
            reverse = {"名称":"name", "代码":"code", "平台":"platform", "资产类型":"asset_type", "市场":"market", "当前市值":"current_value",
                       "成本金额":"cost_amount", "浮盈亏":"profit_amount", "收益率":"profit_rate", "昨日/今日收益":"yesterday_profit",
                       "份额":"holding_share", "最新价":"latest_price", "风险等级":"risk_level", "备注":"note", "导入策略":"duplicate_action"}
            selected = edited[edited["选择"]].drop(columns=["选择"]).rename(columns=reverse)
            selected["code"] = selected.apply(lambda row: row.get("code") or (row.get("推荐基金代码") if row.get("是否写入代码") else ""), axis=1)
            result = import_holding_drafts(selected.fillna("").to_dict("records"))
            st.session_state.pop("ocr_drafts", None)
            rerun_with_message(f"导入完成：新增 {result['inserted']}，覆盖更新 {result['updated']}，跳过 {result['skipped']}，失败 {result['failed']}。")


def profit_screenshot_import_panel() -> None:
    st.info("本次只更新今日收益快照，不会修改持仓成本、交易记录、买卖计划或复盘。第三方估算仅供复盘参考。")
    engine = get_local_ocr_engine(); holdings = fetch_all("holdings")
    if not engine.status.available: st.warning("本地 OCR 不可用，可安装 OCR 依赖后重启，或直接粘贴第三方 App 识别出的文字。")
    files = st.file_uploader("上传实时收益 / 当日收益截图（可多选）", type=["png","jpg","jpeg","webp"], accept_multiple_files=True, key="profit_snapshot_files")
    if files:
        st.write(f"已上传 {len(files)} 张截图")
        cols = st.columns(min(3, len(files)))
        for index, file in enumerate(files): cols[index % len(cols)].image(file.getvalue(), caption=file.name, width="stretch")
    if st.button("识别收益截图", disabled=not bool(files), type="primary"):
        result = engine.recognize_images(files or []); st.session_state["profit_ocr_result"] = result
        if result.get("text"): st.session_state["profit_ocr_text"] = result["text"]
        if result.get("error"): st.warning(result["error"])
    st.session_state.setdefault("profit_ocr_text", "")
    raw_text = st.text_area("OCR 原文（可编辑，也可手动粘贴）", key="profit_ocr_text", height=240)
    if st.button("解析今日收益", disabled=not raw_text.strip()):
        parsed = parse_profit_screenshot_text(raw_text); recommended = recommend_profit_item_codes(parsed["items"], load_fund_code_candidates()); matched = match_profit_items_to_holdings(recommended, holdings)
        st.session_state["profit_parsed"] = parsed; st.session_state["profit_matched"] = matched
        batch_id = insert_row("screenshot_profit_import_batches", {"source_name":parsed["source"], "uploaded_file_count":len(files or []),
            "ocr_engine":engine.status.engine, "status":"parsed", "raw_text":raw_text, "parsed_count":len(matched),
            "matched_count":sum(bool(x.get("holding_id")) for x in matched), "unmatched_count":sum(not x.get("holding_id") for x in matched), "confirmed_count":0})
        st.session_state["profit_batch_id"] = batch_id
    parsed = st.session_state.get("profit_parsed"); matched = st.session_state.get("profit_matched", [])
    if parsed:
        for warning in parsed.get("warnings", []): st.warning(warning)
    if matched:
        options = {"未选择":None, **{f"#{h['id']} {h['name']}":h["id"] for h in holdings}}
        id_to_label = {value:key for key,value in options.items() if value is not None}
        rows = []
        for item in matched:
            rows.append({"是否导入":bool(item.get("holding_id")), "匹配状态":item["match_status"], "本地持仓":id_to_label.get(item.get("holding_id"), "未选择"),
                "基金代码":item.get("code"), "基金名称":item.get("name"), "最新值":item.get("latest_nav"), "涨跌幅":item.get("change_pct"),
                "推荐代码":item.get("recommended_code"), "补全本地代码":False, "当日收益":item.get("daily_pnl"), "持有收益":item.get("holding_pnl"), "持有收益率":item.get("holding_return_pct"),
                "资产金额":item.get("market_value"), "数据来源":parsed["source"], "质量":"第三方估算", "备注":"请人工确认"})
        edited = st.data_editor(pd.DataFrame(rows), hide_index=True, width="stretch", key="profit_snapshot_editor",
            column_config={"本地持仓":st.column_config.SelectboxColumn(options=list(options)), "涨跌幅":st.column_config.NumberColumn(format="%+.2%%"),
                "持有收益率":st.column_config.NumberColumn(format="%+.2%%"), "当日收益":st.column_config.NumberColumn(format="%+.2f"), "持有收益":st.column_config.NumberColumn(format="%+.2f"), "资产金额":st.column_config.NumberColumn(format="¥%.2f")},
            disabled=["匹配状态","基金代码","基金名称","数据来源","质量"])
        if st.button("确认写入今日收益快照", type="primary"):
            imported = skipped = unmatched = 0
            source_items = {str(item.get("code")):item for item in matched}
            holding_map = {h["id"]:h for h in holdings}
            for row in edited.to_dict("records"):
                holding_id = options.get(row["本地持仓"])
                if not row["是否导入"]: skipped += 1; continue
                if not holding_id: unmatched += 1; continue
                item = {**source_items.get(str(row["基金代码"]), {}), "latest_nav":row["最新值"], "change_pct":row["涨跌幅"],
                    "daily_pnl":row["当日收益"], "holding_pnl":row["持有收益"], "holding_return_pct":row["持有收益率"], "market_value":row["资产金额"]}
                save_market_snapshot(build_market_snapshot_from_profit_item(item, holding_map[holding_id], parsed["source"])); imported += 1
                if row.get("补全本地代码") and not holding_map[holding_id].get("code"):
                    apply_confirmed_code_matches([{"holding_id":holding_id, "recommended_code":row.get("推荐代码"), "confirmed":True}])
            batch_id = st.session_state.get("profit_batch_id")
            if batch_id: update_row("screenshot_profit_import_batches", batch_id, {"status":"confirmed", "confirmed_count":imported, "unmatched_count":unmatched})
            account = parsed.get("account", {}); local_total = sum(safe_float(h.get("current_value")) for h in holdings)
            screenshot_total = safe_float(account.get("total_assets"))
            if screenshot_total and local_total and abs(screenshot_total-local_total)/local_total > .1:
                st.warning("截图账户资产与本地持仓合计不一致，请确认是否只截取了部分账户或部分平台。")
            st.success(f"成功导入 {imported} 条，未匹配 {unmatched} 条，跳过 {skipped} 条。本次截图总资产 {format_currency(screenshot_total)}，当日总收益 {format_currency(account.get('daily_pnl') or 0, True)}。")


def screenshot_import_page() -> None:
    page_header("🖼️ 截图导入", "持仓截图用于更新持仓；收益截图只写入今日收益快照。")
    show_flash()
    holding_tab, profit_tab = st.tabs(["持仓截图导入", "今日收益截图导入"])
    with holding_tab: holdings_screenshot_import_panel()
    with profit_tab: profit_screenshot_import_panel()


def plans_page() -> None:
    page_header("📝 买卖计划", "把临场冲动变成事先定义的触发条件和建议动作。")
    show_flash()
    with st.form("add_plan"):
        c1, c2, c3 = st.columns(3)
        asset = c1.text_input("资产名称")
        plan_type = c2.selectbox("计划类型", PLAN_TYPES)
        priority_label = c3.selectbox("优先级", ["高", "中", "低"])
        priority = {"高": 1, "中": 2, "低": 3}[priority_label]
        c1, c2 = st.columns(2)
        condition = c1.text_input("触发条件", placeholder="例如：回调幅度达到")
        trigger = c2.number_input("触发值", value=0.0)
        action = st.text_input("建议动作", placeholder="例如：接回卖出仓位的 30%")
        note = st.text_area("备注")
        if st.form_submit_button("新增计划", type="primary"):
            if not asset.strip(): st.error("资产名称不能为空。")
            else:
                insert_row("plans", {"asset_name": asset.strip(), "plan_type": plan_type, "trigger_condition": condition,
                                      "trigger_value": trigger, "suggested_action": action, "priority": priority, "enabled": 1, "note": note})
                rerun_with_message("计划已新增。")
    plans = fetch_all("plans")
    if not plans:
        st.info("暂无计划。")
        return
    frame = pd.DataFrame(plans)
    frame["状态"] = frame["enabled"].map({1: "🟢 已启用", 0: "⚪ 已停用"})
    st.dataframe(frame[["id", "asset_name", "plan_type", "trigger_condition", "trigger_value", "suggested_action", "priority", "状态", "note"]], width="stretch", hide_index=True)
    choices = {f"#{row['id']} {row['asset_name']} · {row['plan_type']}": row for row in plans}
    label = st.selectbox("选择计划进行操作", list(choices))
    selected = choices[label]
    c1, c2 = st.columns(2)
    if c1.button("停用" if selected["enabled"] else "启用", width="stretch"):
        update_row("plans", selected["id"], {"enabled": 0 if selected["enabled"] else 1})
        rerun_with_message("计划状态已更新。")
    if c2.button("删除计划", width="stretch"):
        delete_row("plans", selected["id"])
        rerun_with_message("计划已删除。")
    with st.expander("编辑所选计划"):
        with st.form(f"edit_plan_{selected['id']}"):
            asset = st.text_input("资产名称", selected["asset_name"])
            kind = st.selectbox("计划类型", PLAN_TYPES, index=PLAN_TYPES.index(selected["plan_type"]) if selected["plan_type"] in PLAN_TYPES else 0)
            condition = st.text_input("触发条件", selected.get("trigger_condition") or "")
            trigger = st.number_input("触发值", value=safe_float(selected.get("trigger_value")))
            action = st.text_input("建议动作", selected.get("suggested_action") or "")
            note = st.text_area("备注", selected.get("note") or "")
            if st.form_submit_button("保存修改", type="primary"):
                update_row("plans", selected["id"], {"asset_name": asset, "plan_type": kind, "trigger_condition": condition,
                                                       "trigger_value": trigger, "suggested_action": action, "note": note})
                rerun_with_message("计划已更新。")


def trades_page() -> None:
    page_header("📒 操作日记", "记录每一次交易、当时情绪与事后结果，避免只记得赢的部分。")
    show_flash()
    plans = fetch_all("plans")
    plan_options = {"无关联计划": None, **{f"#{row['id']} {row['asset_name']} {row['plan_type']}": row["id"] for row in plans}}
    with st.form("add_trade"):
        c1, c2, c3 = st.columns(3)
        trade_date = c1.date_input("日期", date.today())
        asset = c2.text_input("资产名称")
        action = c3.selectbox("操作类型", TRADE_ACTIONS)
        c1, c2, c3 = st.columns(3)
        amount = c1.number_input("金额", min_value=0.0, step=100.0)
        price = c2.number_input("价格", min_value=0.0, step=.0001, format="%.4f")
        emotion = c3.selectbox("当时情绪", EMOTIONS)
        reason = st.text_area("操作原因")
        c1, c2, c3, c4 = st.columns(4)
        plan_label = c1.selectbox("关联计划", list(plan_options))
        review_date = c2.date_input("复盘日期", date.today())
        is_planned = c3.checkbox("按计划执行", value=False)
        confidence = c4.slider("执行前信心", 1, 5, 3)
        discipline = st.slider("纪律分", 1, 5, 3)
        if st.form_submit_button("记录操作", type="primary"):
            if not asset.strip(): st.error("资产名称不能为空。")
            else:
                insert_row("trades", {"trade_date": trade_date.isoformat(), "asset_name": asset.strip(), "action": action,
                                       "amount": amount, "price": price, "reason": reason, "emotion": emotion,
                                       "plan_id": plan_options[plan_label], "is_planned": int(is_planned or plan_options[plan_label] is not None),
                                       "confidence_score": confidence, "discipline_score": discipline,
                                       "review_date": review_date.isoformat(), "review_status": "pending", "review_result": ""})
                rerun_with_message("操作日记已保存。")
    trades = fetch_all("trades", order_by="trade_date DESC, id DESC")
    frame = pd.DataFrame(trades)
    if frame.empty:
        st.info("暂无操作记录。")
        return
    month = date.today().strftime("%Y-%m")
    monthly = frame[frame["trade_date"].astype(str).str.startswith(month)]
    cards = st.columns(5)
    values = [len(monthly), monthly.loc[monthly["action"].isin(["买入", "补仓", "定投"]), "amount"].sum(), monthly.loc[monthly["action"].isin(["卖出", "减仓"]), "amount"].sum(), (monthly["emotion"] == "冲动").sum(), monthly["plan_id"].notna().sum()]
    labels = ["本月操作次数", "本月买入金额", "本月卖出金额", "冲动操作次数", "按计划操作次数"]
    for index, column in enumerate(cards):
        with column: metric_card(labels[index], format_currency(values[index]) if index in (1, 2) else str(int(values[index])))
    c1, c2, c3 = st.columns(3)
    asset_filter = c1.multiselect("按资产筛选", sorted(frame["asset_name"].unique()))
    action_filter = c2.multiselect("按操作类型筛选", TRADE_ACTIONS)
    review_filter = c3.multiselect("按复盘状态筛选", ["pending", "done", "ignored"])
    display = frame
    if asset_filter: display = display[display["asset_name"].isin(asset_filter)]
    if action_filter: display = display[display["action"].isin(action_filter)]
    if review_filter: display = display[display["review_status"].isin(review_filter)]
    st.dataframe(display, width="stretch", hide_index=True)
    st.download_button("导出操作日记 CSV", display.to_csv(index=False).encode("utf-8-sig"), "trades.csv", "text/csv")


def review_page() -> None:
    page_header("🔍 复盘中心", "只复盘已经发生的决策：计划是否执行、错误是否重复、结果是否符合预期。")
    show_flash()
    trades = fetch_all("trades", order_by="trade_date DESC, id DESC")
    summary = get_review_summary(trades)
    cards = st.columns(5)
    for col, label, value in zip(cards, ["待复盘", "已复盘", "按计划占比", "冲动占比", "平均纪律分"],
        [summary["pending_count"], summary["reviewed_count"], summary["planned_count"]/max(summary["total_trades"],1), summary["impulsive_count"]/max(summary["total_trades"],1), summary["average_discipline_score"]]):
        with col: metric_card(label, f"{value:.1%}" if "占比" in label else str(value))
    today = date.today().isoformat()
    pending = [row for row in trades if row.get("review_date") and row["review_date"] <= today and row.get("review_status", "pending") == "pending" and not (row.get("review_result") or "").strip()]
    st.subheader(f"待复盘操作（{len(pending)}）")
    if pending:
        labels = {f"#{row['id']} {row['trade_date']} · {row['asset_name']} · {row['action']}": row for row in pending}
        selected_label = st.selectbox("选择待复盘记录", list(labels))
        selected = labels[selected_label]
        st.info(f"原因：{selected.get('reason') or '未填写'}｜情绪：{selected.get('emotion') or '未填写'}")
        with st.form("quick_review"):
            result_type = st.selectbox("结果类型", ["未判断", "盈利", "亏损", "持平"])
            c1, c2, c3 = st.columns(3)
            result_amount = c1.number_input("结果金额", value=0.0)
            result_rate = c2.number_input("结果收益率 %", value=0.0)
            discipline = c3.slider("纪律分", 1, 5, int(selected.get("discipline_score") or 3))
            mistake_tags = st.multiselect("错误标签", ["追涨", "恐慌割肉", "无计划交易", "仓位过重", "频繁交易", "忽略现金比例", "受新闻影响", "其他"])
            success_tags = st.multiselect("成功标签", ["按计划执行", "分批买入", "分批减仓", "控制仓位", "等待回调", "遵守现金红线", "其他"])
            result = st.text_area("复盘结果 / 经验教训", placeholder="这次操作是否按计划？下次要改什么？")
            if st.form_submit_button("保存复盘", type="primary"):
                update_row("trades", selected["id"], {"review_result": result, "review_status": "done", "result_type": result_type,
                    "result_amount": result_amount, "result_rate": result_rate/100, "mistake_tags": json.dumps(mistake_tags, ensure_ascii=False),
                    "success_tags": json.dumps(success_tags, ensure_ascii=False), "lesson": result, "discipline_score": discipline})
                rerun_with_message("复盘已保存。")
    else:
        st.success("当前没有到期未复盘的操作。")
    st.subheader("复盘统计图表")
    monthly, emotions = pd.DataFrame(get_monthly_review_stats(trades)), pd.DataFrame(get_emotion_stats(trades))
    mistakes, successes = pd.DataFrame(get_mistake_tag_stats(trades)), pd.DataFrame(get_success_tag_stats(trades))
    c1, c2 = st.columns(2)
    if not monthly.empty:
        c1.plotly_chart(px.bar(monthly, x="month", y="trade_count", title="月度操作次数"), width="stretch", config=PLOTLY_CONFIG)
        c2.plotly_chart(px.bar(monthly, x="month", y=["buy_amount", "sell_amount"], barmode="group", title="月度买入 / 卖出金额"), width="stretch", config=PLOTLY_CONFIG)
    c1, c2 = st.columns(2)
    if not emotions.empty: c1.plotly_chart(px.bar(emotions, x="emotion", y=["profit_count", "loss_count"], barmode="group", title="情绪 vs 盈亏"), width="stretch", config=PLOTLY_CONFIG)
    if not mistakes.empty: c2.plotly_chart(px.bar(mistakes, x="tag", y="count", title="错误标签排行"), width="stretch", config=PLOTLY_CONFIG)
    if not successes.empty: st.plotly_chart(px.bar(successes, x="tag", y="count", title="成功标签排行"), width="stretch", config=PLOTLY_CONFIG)
    st.subheader("复盘洞察")
    for insight in generate_review_insights(trades): st.info(insight)
    reviewed = pd.DataFrame([row for row in trades if row.get("review_status") == "done" or (row.get("review_result") or "").strip()])
    if not reviewed.empty:
        st.subheader("历史复盘")
        search = st.text_input("搜索历史复盘")
        if search: reviewed = reviewed[reviewed.astype(str).apply(lambda row: row.str.contains(search, case=False).any(), axis=1)]
        st.dataframe(pd.DataFrame(localize_records(reviewed.to_dict("records"), ["trade_date", "asset_name", "action", "amount", "reason", "emotion", "review_date", "review_result", "discipline_score"])), width="stretch", hide_index=True)


def allocation_page() -> None:
    page_header("⚖️ 资产配置", "比较当前比例与目标区间；偏离只用于提醒，不构成交易指令。")
    show_flash()
    records, frame = holdings_data()
    targets = get_setting("target_allocations", DEFAULT_ALLOCATION)
    total = frame["current_value"].sum() if not frame.empty else 0
    current = frame.groupby("asset_type")["current_value"].sum().to_dict() if not frame.empty else {}
    rows = []
    for asset_type in ASSET_TYPES:
        ratio = current.get(asset_type, 0) / total if total else 0
        target = targets.get(asset_type, {"min": 0, "max": 1})
        status = "低配" if ratio < target["min"] else "超配" if ratio > target["max"] else "正常"
        rows.append({"资产类型": asset_type, "当前占比": ratio, "目标最低%": target["min"] * 100, "目标最高%": target["max"] * 100,
                     "偏离": min(abs(ratio - target["min"]), abs(ratio - target["max"])) if status != "正常" else 0,
                     "状态": "🔴 " + status if status != "正常" and abs(ratio - (target["min"] if status == "低配" else target["max"])) > .05 else "🟡 " + status if status != "正常" else "🟢 正常"})
    edited = st.data_editor(pd.DataFrame(rows), width="stretch", hide_index=True, disabled=["资产类型", "当前占比", "偏离", "状态"],
                            column_config={"当前占比": st.column_config.NumberColumn(format="%.2%%"), "偏离": st.column_config.NumberColumn(format="%.2%%")})
    if st.button("保存目标配置", type="primary"):
        saved = {row["资产类型"]: {"min": safe_float(row["目标最低%"])/100, "max": safe_float(row["目标最高%"])/100} for _, row in edited.iterrows()}
        set_setting("target_allocations", saved)
        rerun_with_message("目标资产配置已保存。")
    fig = go.Figure()
    fig.add_bar(name="当前占比", x=edited["资产类型"], y=edited["当前占比"] * 100)
    fig.add_bar(name="目标中位", x=edited["资产类型"], y=(edited["目标最低%"] + edited["目标最高%"])/2)
    fig.update_layout(barmode="group", yaxis_title="占比 %")
    st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG)


def risk_page() -> None:
    page_header("🚦 风险雷达", "本地规则只负责暴露仓位与行为风险，不预测涨跌。")
    records, frame = holdings_data()
    trades = fetch_all("trades")
    defaults = {"cash_red_ratio": .10, "single_holding_red_ratio": .25, "gold_red_ratio": .25,
                "tech_red_ratio": .35, "high_risk_asset_red_ratio": .50, "weekly_trade_warning": 8, "impulse_warning_ratio": .30}
    settings = get_setting("risk_thresholds", defaults)
    settings["enabled_plan_count"] = sum(p.get("enabled", 1) for p in fetch_all("plans"))
    plans = fetch_all("plans")
    risks = evaluate_risks(records, trades, settings, plans, get_sync_status(), market_snapshots=get_latest_market_snapshots())
    status = risk_summary(risks)
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1: metric_card("总风险分", str(status["risk_score"]))
    with c2: metric_card("整体等级", {"red":"危险", "yellow":"注意", "green":"正常"}[status["level"]])
    with c3: metric_card("🔴 风险", str(status["red_count"]))
    with c4: metric_card("🟡 注意", str(status["yellow_count"]))
    with c5: metric_card("🟢 正常", str(status["green_count"]))
    dimensions = status["dimensions"]
    radar = go.Figure(go.Scatterpolar(r=list(dimensions.values()), theta=list(dimensions), fill="toself", name="风险分"))
    radar.update_layout(polar={"radialaxis": {"visible": True, "range": [0, 35]}}, showlegend=False, title="五维风险评分")
    st.plotly_chart(radar, width="stretch", config=PLOTLY_CONFIG)
    st.subheader("最重要的三条风险")
    risk_cards([item for item in risks if item["level"] != "green"][:3] or risks[:1])
    st.subheader("建议优先动作")
    for item in [item for item in risks if item["level"] != "green"][:3]: st.write(f"- {item['suggestion']}")
    with st.expander("查看全部风险项"):
        risk_cards(risks)
    if not frame.empty:
        c1, c2 = st.columns(2)
        concentration = frame.groupby("asset_type", as_index=False)["current_value"].sum()
        c1.plotly_chart(px.pie(concentration, names="asset_type", values="current_value", hole=.45, title="资产集中度", labels={"asset_type":"资产类型", "current_value":"当前市值"}), width="stretch", config=PLOTLY_CONFIG)
        high = frame.groupby("risk_level", as_index=False)["current_value"].sum()
        c2.plotly_chart(px.bar(high, x="risk_level", y="current_value", color="risk_level", title="高风险资产占比"), width="stretch", config=PLOTLY_CONFIG)
        c1, c2 = st.columns(2)
        c1.plotly_chart(px.bar(frame.sort_values("asset_ratio", ascending=False), x="name", y="asset_ratio", title="单一持仓占比排行"), width="stretch", config=PLOTLY_CONFIG)
        c2.plotly_chart(px.bar(frame.sort_values("profit_amount"), x="name", y="profit_amount", title="浮盈亏排行"), width="stretch", config=PLOTLY_CONFIG)
    if trades:
        tf = pd.DataFrame(trades); tf["trade_date"] = pd.to_datetime(tf["trade_date"], errors="coerce")
        freq = tf.set_index("trade_date").resample("D").size().reset_index(name="次数")
        st.plotly_chart(px.line(freq, x="trade_date", y="次数", title="操作频率"), width="stretch", config=PLOTLY_CONFIG)
    else:
        st.info("暂无操作日记，暂时无法分析操作频率。")
    with st.expander("风险规则配置"):
        with st.form("risk_settings"):
            c1, c2, c3 = st.columns(3)
            cash = c1.number_input("现金红线 %", 0.0, 100.0, settings["cash_red_ratio"]*100)
            single = c2.number_input("单一持仓红线 %", 0.0, 100.0, settings["single_holding_red_ratio"]*100)
            gold = c3.number_input("黄金上限 %", 0.0, 100.0, settings["gold_red_ratio"]*100)
            c1, c2, c3, c4 = st.columns(4)
            tech = c1.number_input("科技上限 %", 0.0, 100.0, settings["tech_red_ratio"]*100)
            high = c2.number_input("高风险资产上限 %", 0.0, 100.0, settings["high_risk_asset_red_ratio"]*100)
            weekly = c3.number_input("近 7 天操作阈值", 1, 100, int(settings["weekly_trade_warning"]))
            impulse = c4.number_input("冲动操作阈值 %", 0.0, 100.0, settings["impulse_warning_ratio"]*100)
            if st.form_submit_button("保存风险阈值"):
                set_setting("risk_thresholds", {"cash_red_ratio":cash/100, "single_holding_red_ratio":single/100, "gold_red_ratio":gold/100,
                    "tech_red_ratio":tech/100, "high_risk_asset_red_ratio":high/100, "weekly_trade_warning":weekly, "impulse_warning_ratio":impulse/100})
                rerun_with_message("风险阈值已保存。")


def daily_report_page() -> None:
    page_header("📰 投资日报", "把持仓、风险、计划与复盘提醒汇总为一份可复制的 Markdown 日报。")
    if st.button("生成日报", type="primary") or "daily_report" not in st.session_state:
        st.session_state["daily_report"] = generate_daily_report()
    report = st.session_state["daily_report"]; o = report["overview"]
    cards = st.columns(4)
    with cards[0]: money_metric("总资产", o["total_asset"])
    with cards[1]: money_metric("总浮盈亏", o["total_profit"], signed=True)
    with cards[2]: rate_metric("现金比例", o["cash_ratio"])
    with cards[3]: metric_card("风险分", str(report["risk_summary"]["risk_score"]))
    if market_snapshot_settings()["show_in_report"]:
        market = {**default_market_snapshot(len(fetch_all("holdings"))), **(report.get("market_snapshot") or {})}
        st.subheader("今日市场快照")
        mc = st.columns(3)
        with mc[0]: money_metric("今日收益合计", market["total_daily_pnl"], signed=True)
        with mc[1]: metric_card("已更新", str(market["matched_count"]))
        with mc[2]: metric_card("未更新", str(market["missing_count"]))
        st.caption(f"数据来源：{market['source_label']} · 最新更新时间：{market['updated_at'] or '暂无'}")
        st.caption("今日收益快照仅供复盘参考，不代表官方最终净值。")
        if not market["available"]: st.info(market["message"])
        if market["available"]:
            with st.expander("查看涨跌与当日亏损排行"):
                rows = []
                for label, values in (("涨幅居前",market["top_gainers"]),("跌幅居前",market["top_losers"]),("当日亏损居前",market["top_daily_losses"])):
                    rows.extend({"类别":label,"名称":x.get("name"),"涨跌幅":x.get("change_pct"),"当日收益":x.get("daily_pnl")} for x in values)
                st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", column_config={"涨跌幅":st.column_config.NumberColumn(format="%+.2%%"),"当日收益":st.column_config.NumberColumn(format="%+.2f")})
    if report["allocations"]:
        allocation = pd.DataFrame(report["allocations"])
        st.plotly_chart(px.pie(allocation, names="asset_type", values="amount", hole=.5, title="资产配置"), width="stretch", config=PLOTLY_CONFIG)
        st.dataframe(pd.DataFrame(localize_records(report["allocations"])), width="stretch", hide_index=True)
    st.subheader("风险列表"); risk_cards(report["risks"])
    st.subheader("启用计划")
    if report["plans"]:
        st.dataframe(pd.DataFrame(localize_records(report["plans"], ["asset_name", "plan_type", "trigger_condition", "trigger_value", "suggested_action", "priority", "note"])), width="stretch", hide_index=True)
    else:
        st.info("暂无启用计划。")
    with st.expander("导出 / 复制日报"):
        st.caption("Markdown 适合复制到备忘录、Obsidian、Notion 或发给 ChatGPT 做复盘；如果你只在本工具里查看，可以不用管。")
        st.code(report["markdown"], language="markdown")
        c1, c2 = st.columns(2)
        if c1.button("保存日报文件", width="stretch"): st.success(f"日报已保存：{save_daily_report(report).name}")
        c2.download_button("下载 Markdown", report["markdown"].encode("utf-8"), f"daily_report_{report['date'].replace('-', '')}.md", "text/markdown", width="stretch")


def sync_page() -> None:
    page_header("🔄 同步与备份", "在设备间同步核心数据，并保留本地备份。")
    st.info("GitHub 用来同步代码和 data/sync/portfolio_sync.json，不同步截图、SQLite 数据库、备份文件和 .env。")
    status = get_sync_status()
    backups = sorted((DATABASE_PATH.parent / "backups").glob("*.db"), reverse=True)[:5]
    st.subheader("当前设备状态")
    cards = st.columns(4)
    git_state = "未配置" if status["git_remote"] == "未配置" else "有改动" if status["git_dirty"] else "已同步"
    data_state = "未导出" if not status["sync_exists"] else "有本地改动" if status["possibly_out_of_sync"] else git_state
    for col, label, value in zip(cards, ["当前设备", "数据状态", "最近同步时间", "最近备份时间"],
        [status["os"], data_state, status["sync_exported_at"] or "尚未同步", datetime.fromtimestamp(backups[0].stat().st_mtime).strftime("%Y-%m-%d %H:%M") if backups else "尚未备份"]):
        with col: metric_card(label, value)
    if status["possibly_out_of_sync"]: st.warning("本地数据库比同步快照新，导入可能覆盖本机较新的数据。")
    st.subheader("操作")
    c1, c2, c3 = st.columns(3)
    if c1.button("导出本机数据", type="primary", width="stretch"):
        result = export_sync_snapshot(); st.success(f"导出完成，共 {sum(result['counts'].values())} 条记录。")
    if c2.button("预览同步数据", width="stretch"):
        st.session_state["sync_preview"] = import_sync_snapshot("preview")
    if st.session_state.get("sync_preview"):
        preview = st.session_state["sync_preview"]
        st.write(f"同步文件包含 {sum(preview['counts'].values())} 条记录。" if not preview["errors"] else "同步文件存在问题，请查看高级信息。")
    mode = st.radio("导入模式", ["merge", "overwrite"], format_func=lambda x: "合并（同 ID 更新）" if x == "merge" else "覆盖（清空核心表后导入）", horizontal=True)
    confirmed = st.checkbox("我已确认导入；覆盖模式将替换本地核心数据")
    if st.button("导入同步数据", disabled=not confirmed, type="primary"):
        result = import_sync_snapshot(mode)
        (st.error if result["errors"] else st.success)(f"导入完成：新增 {result['inserted']}，更新 {result['updated']}，跳过 {result['skipped']}。")
    c1, c2, c3 = st.columns(3)
    if c1.button("提交并推送 GitHub", width="stretch"):
        result = run_git_action("push"); (st.success if result["ok"] else st.error)(result["message"])
    if c2.button("拉取 GitHub 最新代码", width="stretch"):
        result = run_git_action("pull"); (st.success if result["ok"] else st.error)(result["message"])
    if c3.button("手动备份", width="stretch"):
        st.success(f"备份完成：{backup_database().name}")
    with st.expander("查看备份"): st.write([path.name for path in backups] or "暂无备份")
    with st.expander("高级信息"):
        st.write({"数据库路径": status["database_path"], "同步文件路径": status["sync_path"], "Git remote": status["git_remote"],
                  "分支": status["git_branch"], "hostname": status["device"], "exported_at": status["sync_exported_at"],
                  "备份路径": [str(path) for path in backups]})
        if st.session_state.get("sync_preview"): st.json(st.session_state["sync_preview"])


def github_sync_page() -> None:
    page_header("🐙 GitHub 同步", "这里只提供可复制的 Git 命令，不会在页面中保存 token。")
    st.code('git pull\npython scripts/git_sync.py "sync portfolio snapshot"', language="bash")
    st.caption("先在“数据同步”导出 JSON，再提交推送；另一台设备 pull 后预览并导入。")


def settings_page() -> None:
    page_header("⚙️ 设置", "管理本地偏好、OCR 状态和风险参数。")
    show_flash()
    engine = get_local_ocr_engine()
    c1, c2, c3 = st.columns(3)
    with c1: metric_card("当前版本", APP_VERSION)
    with c2: metric_card("数据存储", "本机本地")
    with c3: metric_card("OCR 状态", "🟢 可用" if engine.status.available else "🟡 未安装")
    st.subheader("市场快照设置")
    market_settings = market_snapshot_settings()
    with st.form("market_snapshot_settings_form"):
        check_on_open = st.checkbox("页面打开时检查市场快照状态", value=market_settings["check_on_open"])
        auto_refresh = st.checkbox("页面打开时自动刷新市场快照", value=market_settings["auto_refresh"], help="默认关闭，避免页面打开变慢。")
        c1, c2 = st.columns(2)
        interval = c1.number_input("最小刷新间隔（分钟）", min_value=15, max_value=1440, value=int(market_settings["min_interval_minutes"]))
        api_source = c2.selectbox("API 数据源", ["akshare"], index=0)
        screenshot_priority = st.checkbox("第三方截图优先于 API", value=market_settings["screenshot_priority"])
        show_columns = st.checkbox("在持仓表格展示今日收益列", value=market_settings["show_holding_columns"])
        show_report = st.checkbox("在投资日报展示今日市场快照", value=market_settings["show_in_report"])
        if st.form_submit_button("保存市场快照设置"):
            set_setting("market_snapshot_settings", {"check_on_open":check_on_open, "auto_refresh":auto_refresh,
                "min_interval_minutes":interval, "api_source":api_source, "screenshot_priority":screenshot_priority,
                "show_holding_columns":show_columns, "show_in_report":show_report})
            rerun_with_message("市场快照设置已保存。")
    st.caption("AKShare 是可选能力；未安装或网络不可用时，仍可通过第三方 App 收益截图更新。场外基金净值通常不是盘中实时官方数据。")
    st.subheader("数据操作")
    c1, c2 = st.columns(2)
    if c1.button("初始化 demo 数据", width="stretch"):
        seed_demo_data(); rerun_with_message("Demo 数据已初始化；已有持仓时不会重复写入。")
    if c2.button("重置为 demo 数据", width="stretch"):
        clear_tables(["holdings", "trades", "plans", "rules", "ocr_import_batches", "app_settings"])
        seed_demo_data(skip_if_holdings_exist=False); rerun_with_message("数据已重置为模拟数据。")
    c1, c2 = st.columns(2)
    if c1.button("导出完整 SQLite 备份", width="stretch"):
        path = backup_database(); st.success(f"已备份到：{path}")
    if c2.button("导出 holdings/trades/plans/rules CSV 压缩包", width="stretch"):
        path = export_all_csv_zip(); st.success(f"已导出到：{path}")
    st.warning("免责声明：本项目仅用于个人投资记录和辅助决策，不构成投资建议，不保证收益，不自动交易。")
    with st.expander("高级信息"):
        st.write(f"数据库路径：{DATABASE_PATH}")


PAGES = {
    "总览": dashboard_page,
    "持仓工作台": holdings_page,
    "截图导入": screenshot_import_page,
    "投资日报": daily_report_page,
    "风险雷达": risk_page,
    "复盘中心": review_page,
    "同步与备份": sync_page,
    "设置": settings_page,
}

with st.sidebar:
    st.markdown("# 🧭 投资驾驶舱")
    st.caption("本地记录 · 仓位纪律 · 人工决策")
    selected_page = st.radio("导航", list(PAGES), label_visibility="collapsed", key="navigation")
    st.divider()
    st.caption(f"v{APP_VERSION} · SQLite 本地存储")
    st.caption("不联网抓行情 · 不自动交易")

PAGES[selected_page]()
