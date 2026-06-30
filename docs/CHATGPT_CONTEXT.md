# ChatGPT Context

`personal-investment-dashboard` 是本地个人投资驾驶舱，项目路径为 `D:\AAA-Projects\personal-investment-dashboard`，Windows venv 建议放在 `D:\AAA-Projects\.venvs\personal-investment-dashboard`。

技术栈：Python、Streamlit、SQLite、Pandas、Plotly、Pillow；RapidOCR 是可选依赖。入口是 `app.py`，数据库是 `data/investment_dashboard.db`。

主功能包括持仓、资产配置、风险雷达、买卖计划、操作日记、复盘，以及支付宝基金/理财/黄金截图导入。OCR 或解析结果必须人工确认；OCR 不可用时允许手动粘贴文本。

边界：不接 OpenAI API，不抓行情，不接券商，不自动交易，不保证收益。真实数据库、截图、备份、导出、`.env` 和账户信息不得提交 Git。

接手时先读 `docs/AI_HANDOFF.md` 和 `docs/PROJECT_STATE.md`，运行 `pytest`，然后执行 `streamlit run app.py`。数据库变更要兼容旧数据；parser 变更必须补测试。
# v0.2.0 上下文

当前新增数据同步、投资日报、风险评分和复盘统计。可提交的数据文件仅为 `data/sync/portfolio_sync.json`；`data/investment_dashboard.db`、`data/uploads/`、`data/backups/`、`data/exports/`、截图、日志、`.env` 和 token 不提交。跨设备顺序为：拉取代码 → 启动应用 → 预览/导入；修改后导出快照 → 提交推送。项目仅做个人记录和辅助决策，不构成投资建议，不保证收益，不自动交易。
