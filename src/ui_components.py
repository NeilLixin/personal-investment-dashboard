from __future__ import annotations

import streamlit as st

from src.calculations import format_currency, format_rate


CUSTOM_CSS = """
<style>
  .stApp { background: #f5f7fb; }
  [data-testid="stSidebar"] { background: linear-gradient(180deg,#102a43,#1d4d6f); }
  [data-testid="stSidebar"] * { color: #f8fafc; }
  .hero { padding: 1.2rem 1.4rem; border-radius: 18px; color: white; margin-bottom: 1rem;
          background: linear-gradient(135deg,#12395b,#1f7a67); box-shadow: 0 10px 30px rgba(16,42,67,.16); }
  .hero h1 { margin: 0; font-size: 2rem; } .hero p { margin: .35rem 0 0; opacity: .85; }
  .metric-card { background:white; border:1px solid #e3e8ef; border-radius:14px; padding:16px;
                 box-shadow:0 4px 14px rgba(16,42,67,.06); min-height:112px; }
  .metric-label { color:#64748b; font-size:.88rem; }.metric-value { font-size:1.55rem; font-weight:750; color:#102a43; margin-top:6px; }
  .positive { color:#0f8a5f; }.negative { color:#c43d3d; }
  .risk-card { background:white; border-left:5px solid #eab308; border-radius:10px; padding:12px 14px; margin:.5rem 0; }
  .risk-danger { border-left-color:#dc2626; }.risk-normal { border-left-color:#16a34a; }
  div[data-testid="stDataFrame"] { border:1px solid #e3e8ef; border-radius:12px; overflow:hidden; }
  .small-muted { color:#64748b; font-size:.88rem; }
</style>
"""


def inject_css() -> None:
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def page_header(title: str, subtitle: str) -> None:
    st.markdown(f'<div class="hero"><h1>{title}</h1><p>{subtitle}</p></div>', unsafe_allow_html=True)


def section_title(title: str, help_text: str = "") -> None:
    st.subheader(title)
    if help_text: st.caption(help_text)


def status_badge(text: str, level: str = "green") -> str:
    icons = {"green":"🟢", "yellow":"🟡", "red":"🔴"}
    return f"{icons.get(level, '🟢')} {text}"


def empty_state(message: str) -> None:
    st.info(message)


def compact_help(message: str) -> None:
    st.caption(message)


def risk_badge(level: str) -> str:
    return status_badge({"green":"正常", "yellow":"注意", "red":"危险"}.get(level, level), level)


def money_format(value: float, signed: bool = False) -> str:
    return format_currency(value, signed)


def percent_format(value: float, signed: bool = False) -> str:
    return format_rate(value, signed)


def advanced_expander(label: str = "高级信息"):
    return st.expander(label, expanded=False)


def metric_card(label: str, value: str, tone: str = "") -> None:
    st.markdown(f'<div class="metric-card"><div class="metric-label">{label}</div><div class="metric-value {tone}">{value}</div></div>', unsafe_allow_html=True)


def money_metric(label: str, value: float, signed: bool = False) -> None:
    metric_card(label, format_currency(value, signed), "positive" if value > 0 and signed else "negative" if value < 0 else "")


def rate_metric(label: str, value: float, signed: bool = False) -> None:
    metric_card(label, format_rate(value, signed), "positive" if value > 0 and signed else "negative" if value < 0 else "")


def risk_cards(items: list[dict]) -> None:
    for item in items:
        css = "risk-danger" if item["level"] in ("danger", "red") else "risk-normal" if item["level"] in ("normal", "green") else ""
        st.markdown(
            f'<div class="risk-card {css}"><b>{item["icon"]} {item["title"]}</b><br>{item["message"]}'
            f'<div class="small-muted">建议：{item["suggestion"]}</div></div>', unsafe_allow_html=True,
        )


PLOTLY_CONFIG = {"displaylogo": False, "responsive": True}
