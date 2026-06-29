# Project State

## 当前状态

v0.1.0 MVP 已完成，项目可本地启动。首次启动自动建立 SQLite 数据库；可通过设置页或脚本加载隐私安全的 demo 数据。

## 已完成功能

- 九个 Streamlit 页面和现代中文卡片式 UI。
- 持仓 CRUD、筛选、CSV 导入导出和自动计算。
- 多截图预览、可选 OCR、手动文本、支付宝解析、确认导入和批次记录。
- 买卖计划 CRUD/启停、操作日记、到期复盘和基础统计。
- 资产配置目标、Plotly 图表、本地风险规则。
- SQLite/CSV 备份、demo 数据和 GitHub 同步脚本。
- 计算、支付宝解析和风险规则测试。

## 未完成功能

- 未接实时行情、券商和自动交易（有意不做）。
- OCR parser 尚未覆盖所有支付宝页面变体。
- 暂无价格快照历史和复杂绩效归因。
- 暂无多用户、登录或公网部署支持。

## 重要路径

- `app.py`：Streamlit 入口。
- `src/database.py`：数据库。
- `src/calculations.py`：投资组合计算。
- `src/rule_engine.py`：风险规则。
- `src/ocr_engine.py`、`src/alipay_parser.py`：截图识别与解析。
- `data/investment_dashboard.db`：本地数据库，不提交。

## 最近变更

- 2026-06-29：初始化 v0.1.0 完整 MVP、文档、脚本和测试。
