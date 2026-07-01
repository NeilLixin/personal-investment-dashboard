# ChatGPT Context

`personal-investment-dashboard` 是本地个人投资驾驶舱，项目路径为 `D:\AAA-Projects\personal-investment-dashboard`，Windows venv 建议放在 `D:\AAA-Projects\.venvs\personal-investment-dashboard`。

技术栈：Python、Streamlit、SQLite、Pandas、Plotly、Pillow；RapidOCR 是可选依赖。入口是 `app.py`，数据库是 `data/investment_dashboard.db`。

主功能包括持仓、资产配置、风险雷达、买卖计划、操作日记、复盘，以及支付宝基金/理财/黄金截图导入。
支付宝基金采用图片预处理、RapidOCR boxes、三列坐标解析和人工确认；OCR 不可用时允许普通 OCR
或手动粘贴文本，金额始终必须人工核对。

边界：不接 OpenAI API，不抓行情，不接券商，不自动交易，不保证收益。真实数据库、截图、备份、导出、`.env` 和账户信息不得提交 Git。

接手时先读 `docs/AI_HANDOFF.md` 和 `docs/PROJECT_STATE.md`，运行 `pytest`，然后执行 `streamlit run app.py`。数据库变更要兼容旧数据；parser 变更必须补测试。
## v0.3.0 上下文

新增 image_preprocess.py 和 alipay_fund_parser.py。支付宝专用解析器按 x 坐标区分名称、金额/
昨日收益、持有收益/率，并按基金名 y 坐标划分行；广告、标签和底部导航会被忽略。chicang
仅用于参考 OCR 确认导入思路，Umi-OCR 与 zocr 仅是未来备用后端候选，当前不引入其源码或依赖。

# v0.2.0 上下文

当前新增数据同步、投资日报、风险评分和复盘统计。可提交的数据文件仅为 `data/sync/portfolio_sync.json`；`data/investment_dashboard.db`、`data/uploads/`、`data/backups/`、`data/exports/`、截图、日志、`.env` 和 token 不提交。跨设备顺序为：拉取代码 → 启动应用 → 预览/导入；修改后导出快照 → 提交推送。项目仅做个人记录和辅助决策，不构成投资建议，不保证收益，不自动交易。
# v0.4.0 当前上下文

截图导入已经产品化：上传后自动识别支付宝基金或东方财富，解析后必须通过统一中文表格人工确认。
普通界面隐藏 OCR 原文、box、路径和 JSON；高级调试模式保留排查能力。投资日报列名中文化，
数据同步页面向普通用户，风险雷达使用仓位、收益、交易行为、复盘纪律、数据质量五维评分。
这些功能只做本地记录和规则提醒，不构成投资建议，不预测行情、不自动交易。

## v0.5.0 当前上下文

前台已重构为八个主入口。持仓工作台承担筛选、分组、快速操作、计划、历史记录、复盘和设置；资产配置
融入总览与风险判断；同步、GitHub 和备份合并。重复截图默认按平台范围唯一键覆盖，历史交易与计划保留。
项目仍是 Python + Streamlit + SQLite，当前不使用 React。
