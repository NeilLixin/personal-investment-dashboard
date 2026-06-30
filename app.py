from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.alipay_parser import parse_alipay_text
from src.calculations import calculate_profit, enrich_holdings, format_currency, format_rate, portfolio_summary, safe_float
from src.config import (
    APP_VERSION, ASSET_TYPES, DATABASE_PATH, EMOTIONS, MARKETS, PLAN_TYPES, PLATFORMS,
    RISK_LEVELS, TRADE_ACTIONS, ensure_directories,
)
from src.database import (
    clear_tables, delete_row, fetch_all, get_row, get_setting, init_db, insert_row,
    now_text, set_setting, update_row,
)
from src.export_service import backup_database, export_all_csv_zip
from src.import_service import import_holding_drafts, parsed_to_drafts
from src.ocr_engine import LocalOCREngine
from src.rule_engine import evaluate_risks, risk_summary, system_suggestions
from src.report_service import generate_daily_report, save_daily_report
from src.review_service import (
    generate_review_insights, get_emotion_stats, get_mistake_tag_stats,
    get_monthly_review_stats, get_review_summary, get_success_tag_stats,
)
from src.sync_service import export_sync_snapshot, get_sync_status, import_sync_snapshot
from src.sample_data import DEFAULT_ALLOCATION, seed_demo_data
from src.ui_components import PLOTLY_CONFIG, inject_css, metric_card, money_metric, page_header, rate_metric, risk_cards


st.set_page_config(page_title="个人投资驾驶舱", page_icon="🧭", layout="wide", initial_sidebar_state="expanded")
ensure_directories()
init_db()
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
    if frame.empty:
        st.info("暂无持仓。可以先到“数据备份/设置”初始化 demo 数据，或前往“持仓管理”录入。")
        return
    left, right = st.columns(2)
    with left:
        allocation = frame.groupby("asset_type", as_index=False)["current_value"].sum()
        fig = px.pie(allocation, names="asset_type", values="current_value", hole=.55, title="资产类型配置")
        st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG)
    with right:
        platforms = frame.groupby("platform", as_index=False)["current_value"].sum()
        fig = px.bar(platforms, x="platform", y="current_value", color="platform", title="平台资产分布")
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
    page_header("📦 持仓管理", "录入、筛选和维护全部资产；收益率与资产占比自动计算。")
    show_flash()
    records, frame = holdings_data()
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
        st.info("暂无持仓。")
        return
    c1, c2, c3 = st.columns(3)
    platform_filter = c1.multiselect("平台筛选", sorted(frame["platform"].dropna().unique()))
    type_filter = c2.multiselect("资产类型筛选", sorted(frame["asset_type"].dropna().unique()))
    sort_key = c3.selectbox("排序", ["市值从高到低", "收益从高到低", "收益从低到高"])
    display = frame.copy()
    if platform_filter: display = display[display["platform"].isin(platform_filter)]
    if type_filter: display = display[display["asset_type"].isin(type_filter)]
    display = display.sort_values("current_value" if sort_key == "市值从高到低" else "profit_amount", ascending=sort_key == "收益从低到高")
    shown = display[["id", "name", "code", "platform", "asset_type", "current_value", "cost_amount", "profit_amount", "profit_rate", "asset_ratio", "display_status"]].copy()
    shown.columns = ["ID", "名称", "代码", "平台", "资产类型", "当前市值", "成本", "浮盈亏", "收益率", "资产占比", "状态"]
    st.dataframe(shown, width="stretch", hide_index=True, column_config={"当前市值": st.column_config.NumberColumn(format="¥%.2f"), "成本": st.column_config.NumberColumn(format="¥%.2f"), "浮盈亏": st.column_config.NumberColumn(format="¥%.2f"), "收益率": st.column_config.NumberColumn(format="%.2%%"), "资产占比": st.column_config.NumberColumn(format="%.2%%")})
    st.subheader("编辑 / 删除")
    choices = {f"#{row['id']} {row['name']}": int(row["id"]) for row in records}
    selected_label = st.selectbox("选择持仓", list(choices))
    selected_id = choices[selected_label]
    initial = get_row("holdings", selected_id)
    with st.expander("编辑所选持仓"):
        payload = holding_form(f"edit_holding_{selected_id}", initial)
        if payload:
            save_holding(payload, selected_id)
            rerun_with_message("持仓已更新。")
    if st.button("删除所选持仓", type="secondary"):
        delete_row("holdings", selected_id)
        rerun_with_message("持仓已删除。")


def screenshot_import_page() -> None:
    page_header("🖼️ 截图导入", "支持支付宝基金、黄金和理财截图；所有解析结果必须人工确认后才入库。")
    show_flash()
    st.info(
        "无法自动 OCR 时：① 执行 `pip install -r requirements-ocr.txt`；② 安装后重启 Streamlit；"
        "③ 仍不可用可使用 iPhone/支付宝的文字识别并粘贴到下方文本框；④ OCR 金额必须人工确认后才能导入。"
    )
    engine = get_local_ocr_engine()
    status = engine.status
    c1, c2, c3 = st.columns(3)
    with c1: metric_card("OCR 引擎", status.engine)
    with c2: metric_card("OCR 状态", "🟢 可用" if status.available else "🔴 初始化失败" if status.state == "initialization_failed" else "🟡 不可用")
    with c3: metric_card("识别方式", "本机离线识别")
    if status.available:
        st.success(f"{status.message}（{status.engine}）")
    elif status.state == "initialization_failed":
        st.error(f"{status.message}：{status.error or '未知错误'}")
    else:
        st.warning(f"{status.message}。上传后仍可点击 OCR 按钮查看处理建议，或直接手动粘贴文字。")
    with st.expander("OCR 安装与排查"):
        st.code("pip install -r requirements-ocr.txt", language="bash")
        st.caption("安装完成后必须停止并重新启动 Streamlit。基础页面不依赖 OCR，安装失败也可以继续手动粘贴文字。")

    auto_ocr = st.toggle("上传后自动 OCR", value=False, help="默认关闭；大图或多图识别可能需要一些时间。")
    files = st.file_uploader("上传支付宝持仓截图（可多选）", type=["png", "jpg", "jpeg", "webp"], accept_multiple_files=True)
    if files:
        st.write(f"**已上传 {len(files)} 张图片**")
        st.write("文件名：" + "、".join(file.name for file in files))
        columns = st.columns(min(3, len(files)))
        for index, file in enumerate(files):
            columns[index % len(columns)].image(file.getvalue(), caption=file.name, width="stretch")
            file.seek(0)

    def run_ocr() -> None:
        with st.spinner(f"正在使用 {status.engine} 逐张识别，请稍候……"):
            result = engine.recognize_images(files or [])
        st.session_state["ocr_results"] = result
        if result["text"]:
            st.session_state["ocr_raw_text"] = result["text"]
        if not result["ok"]:
            st.error(result["error"] or f"OCR 不可用。请执行 pip install -r requirements-ocr.txt，安装后重启 Streamlit。")
        elif result["error"]:
            st.warning("部分图片识别失败，但成功结果已保留：" + result["error"])
        else:
            st.success(f"OCR 完成：成功识别 {result['details']['success_count']} 张图片。")

    signature = tuple((file.name, getattr(file, "size", len(file.getvalue()))) for file in (files or []))
    should_auto_run = bool(files and auto_ocr and st.session_state.get("ocr_auto_signature") != signature)
    if should_auto_run:
        st.session_state["ocr_auto_signature"] = signature
        run_ocr()
    if st.button("开始本地 OCR", disabled=not bool(files), type="primary", help="上传图片后可点击；依赖缺失时会显示安装方法。"):
        run_ocr()

    ocr_result = st.session_state.get("ocr_results")
    if ocr_result and ocr_result.get("details", {}).get("results"):
        st.subheader("逐张 OCR 结果")
        for index, item in enumerate(ocr_result["details"]["results"]):
            icon = "✅" if item["ok"] else "❌"
            with st.expander(f"{icon} {item['name']}", expanded=not item["ok"]):
                if item["ok"]:
                    st.text(item["text"] or "未识别到文字")
                else:
                    st.error(item["error"])

    st.session_state.setdefault("ocr_raw_text", "")
    raw_text = st.text_area("OCR 原文 / 手动粘贴 OCR 文本", key="ocr_raw_text", height=260,
                            help="OCR 结果会自动填入；可以直接修正错字，也可以完全手动粘贴文字。")
    if st.button("解析持仓", type="primary", disabled=not raw_text.strip()):
        parsed = parse_alipay_text(raw_text)
        st.session_state["ocr_drafts"] = parsed_to_drafts(parsed)
        batch_id = insert_row("ocr_import_batches", {"source_platform": "支付宝", "image_count": len(files or []),
                                                       "raw_text": raw_text, "parsed_json": json.dumps(parsed, ensure_ascii=False),
                                                       "status": "pending"})
        st.session_state["ocr_batch_id"] = batch_id
        if not parsed:
            st.warning("没有解析出完整持仓。请检查产品名称和持有金额，或手动整理文本后重试。")
    drafts = st.session_state.get("ocr_drafts")
    if isinstance(drafts, pd.DataFrame) and not drafts.empty:
        st.subheader("确认导入")
        st.caption("请核对并修改字段；同名或同代码持仓可选择覆盖、新增或跳过。")
        edited = st.data_editor(
            drafts, width="stretch", num_rows="dynamic", key="ocr_editor",
            column_config={
                "platform": st.column_config.SelectboxColumn(options=PLATFORMS),
                "asset_type": st.column_config.SelectboxColumn(options=ASSET_TYPES),
                "market": st.column_config.SelectboxColumn(options=MARKETS),
                "risk_level": st.column_config.SelectboxColumn(options=RISK_LEVELS),
                "duplicate_action": st.column_config.SelectboxColumn("重复项处理", options=["覆盖更新", "新增一条", "跳过"]),
            },
        )
        if st.button("确认导入持仓", type="primary"):
            result = import_holding_drafts(edited.fillna("").to_dict("records"))
            batch_id = st.session_state.get("ocr_batch_id")
            if batch_id:
                update_row("ocr_import_batches", batch_id, {"parsed_json": edited.to_json(orient="records", force_ascii=False), "status": "imported"})
            st.session_state.pop("ocr_drafts", None)
            rerun_with_message(f"截图导入完成：新增 {result['inserted']}，更新 {result['updated']}，跳过 {result['skipped']}。")


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
        st.dataframe(reviewed, width="stretch", hide_index=True)


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
    risks = evaluate_risks(records, trades, settings)
    status = risk_summary(risks)
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1: metric_card("总风险分", str(status["risk_score"]))
    with c2: metric_card("整体等级", {"red":"危险", "yellow":"注意", "green":"正常"}[status["level"]])
    with c3: metric_card("🔴 风险", str(status["red_count"]))
    with c4: metric_card("🟡 注意", str(status["yellow_count"]))
    with c5: metric_card("🟢 正常", str(status["green_count"]))
    risk_cards(risks)
    if not frame.empty:
        c1, c2 = st.columns(2)
        concentration = frame.groupby("asset_type", as_index=False)["current_value"].sum()
        c1.plotly_chart(px.pie(concentration, names="asset_type", values="current_value", hole=.45, title="资产集中度"), width="stretch", config=PLOTLY_CONFIG)
        high = frame.groupby("risk_level", as_index=False)["current_value"].sum()
        c2.plotly_chart(px.bar(high, x="risk_level", y="current_value", color="risk_level", title="高风险资产占比"), width="stretch", config=PLOTLY_CONFIG)
    if trades:
        tf = pd.DataFrame(trades); tf["trade_date"] = pd.to_datetime(tf["trade_date"], errors="coerce")
        freq = tf.set_index("trade_date").resample("D").size().reset_index(name="次数")
        st.plotly_chart(px.line(freq, x="trade_date", y="次数", title="操作频率"), width="stretch", config=PLOTLY_CONFIG)
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
    if report["allocations"]:
        allocation = pd.DataFrame(report["allocations"])
        st.plotly_chart(px.pie(allocation, names="asset_type", values="amount", hole=.5, title="资产配置"), width="stretch", config=PLOTLY_CONFIG)
        st.dataframe(allocation, width="stretch", hide_index=True)
    st.subheader("风险列表"); risk_cards(report["risks"])
    st.subheader("启用计划")
    if report["plans"]:
        st.dataframe(pd.DataFrame(report["plans"]), width="stretch", hide_index=True)
    else:
        st.info("暂无启用计划。")
    st.subheader("复制版 Markdown")
    st.code(report["markdown"], language="markdown")
    c1, c2 = st.columns(2)
    if c1.button("保存日报", width="stretch"): st.success(f"已保存：{save_daily_report(report)}")
    c2.download_button("下载 Markdown", report["markdown"].encode("utf-8"), f"daily_report_{report['date'].replace('-', '')}.md", "text/markdown", width="stretch")


def sync_page() -> None:
    page_header("🔄 数据同步", "用可审查的 JSON 快照在 Mac 与 Windows 之间同步核心数据。")
    st.warning("结构化持仓数据会写入 data/sync/portfolio_sync.json 并提交到私有 GitHub。不会同步截图、.env、token、SQLite、备份和导出文件。私有仓库也不是绝对安全，切勿设为 public。")
    status = get_sync_status()
    cards = st.columns(4)
    for col, label, value in zip(cards, ["当前设备 / 系统", "同步文件", "同步来源", "Git 状态"],
        [f"{status['device']} / {status['os']}", "已存在" if status['sync_exists'] else "不存在", status['sync_source'] or "尚未导出", f"{status['git_branch']} · {'有改动' if status['git_dirty'] else '干净'}"]):
        with col: metric_card(label, value)
    st.write(f"数据库：`{status['database_path']}`  ·  同步文件：`{status['sync_path']}`")
    st.write(f"本地更新时间：{status['local_updated_at'] or '无'}  ·  快照导出时间：{status['sync_exported_at'] or '无'}  ·  remote：{status['git_remote']}")
    if status["possibly_out_of_sync"]: st.warning("本地数据库比同步快照新，导入可能覆盖本机较新的数据。")
    c1, c2 = st.columns(2)
    if c1.button("导出本机数据到同步文件", type="primary", width="stretch"):
        result = export_sync_snapshot(); st.success(f"导出完成：{result['counts']} → {result['file_path']}")
    if c2.button("预览同步文件", width="stretch"):
        st.session_state["sync_preview"] = import_sync_snapshot("preview")
    if st.session_state.get("sync_preview"):
        st.json(st.session_state["sync_preview"])
    mode = st.radio("导入模式", ["merge", "overwrite"], format_func=lambda x: "合并（同 ID 更新）" if x == "merge" else "覆盖（清空核心表后导入）", horizontal=True)
    confirmed = st.checkbox("我已确认导入；覆盖模式将替换本地核心数据")
    if st.button("从同步文件导入到本机", disabled=not confirmed, type="primary"):
        result = import_sync_snapshot(mode); st.json(result)
        (st.error if result["errors"] else st.success)("导入完成，请查看统计与错误列表。")
    backups = sorted((DATABASE_PATH.parent / "backups").glob("*.db"), reverse=True)[:5]
    with st.expander("最近备份"): st.write([str(path) for path in backups] or "暂无备份")
    st.info("一键流程：公司 Mac 导出 → GitHub 同步页提交推送；家里 Windows git pull → 本页预览 → 确认导入。")


def github_sync_page() -> None:
    page_header("🐙 GitHub 同步", "这里只提供可复制的 Git 命令，不会在页面中保存 token。")
    st.code('git pull\npython scripts/git_sync.py "sync portfolio snapshot"', language="bash")
    st.caption("先在“数据同步”导出 JSON，再提交推送；另一台设备 pull 后预览并导入。")


def settings_page() -> None:
    page_header("🗄️ 数据备份 / 设置", "所有资产数据默认只保存在本地 SQLite；导出文件也不会自动上传。")
    show_flash()
    engine = get_local_ocr_engine()
    c1, c2, c3 = st.columns(3)
    with c1: metric_card("当前版本", APP_VERSION)
    with c2: metric_card("数据库", str(DATABASE_PATH))
    with c3: metric_card("OCR 状态", "🟢 可用" if engine.status.available else "🟡 未安装")
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
    st.subheader("GitHub 同步说明")
    st.code('python scripts\\git_sync.py "update dashboard"', language="powershell")
    st.caption("数据库、截图、备份、导出文件和 .env 已被 .gitignore 排除。脚本不会设置全局代理。")
    st.warning("免责声明：本项目仅用于个人投资记录和辅助决策，不构成投资建议，不保证收益，不自动交易。")


PAGES = {
    "总览 Dashboard": dashboard_page,
    "持仓管理": holdings_page,
    "截图导入": screenshot_import_page,
    "投资日报": daily_report_page,
    "买卖计划": plans_page,
    "操作日记": trades_page,
    "复盘中心": review_page,
    "资产配置": allocation_page,
    "风险雷达": risk_page,
    "数据同步": sync_page,
    "GitHub 同步": github_sync_page,
    "数据备份/设置": settings_page,
}

with st.sidebar:
    st.markdown("# 🧭 投资驾驶舱")
    st.caption("本地记录 · 仓位纪律 · 人工决策")
    selected_page = st.radio("导航", list(PAGES), label_visibility="collapsed", key="navigation")
    st.divider()
    st.caption(f"v{APP_VERSION} · SQLite 本地存储")
    st.caption("不联网抓行情 · 不自动交易")

PAGES[selected_page]()
