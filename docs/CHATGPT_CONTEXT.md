# ChatGPT / Codex 接手摘要

`personal-investment-dashboard` 是本地个人投资驾驶舱，用于管理持仓、记录交易和计划、完成复盘、生成投资日报、提示仓位与行为风险，并通过私有 GitHub 在 Mac 与 Windows 间同步结构化数据。它不接券商、不自动交易、不预测涨跌，也不构成投资建议。

技术栈为 Python 3.11、Streamlit、SQLite、Pandas、Plotly、Pillow 和 pytest，RapidOCR 是可选依赖。当前不要用 React/Vue/FastAPI 重写；核心能力是 Python OCR、截图解析、本地数据库和规则计算，Streamlit 更适合继续快速迭代。

Mac 项目路径：`/Users/lixin/personal-investment-dashboard`，虚拟环境：`/Users/lixin/.venvs/personal-investment-dashboard`。Windows 项目路径：`D:\AAA-Projects\personal-investment-dashboard`，虚拟环境：`D:\AAA-Projects\.venvs\personal-investment-dashboard`。激活环境后运行 `python scripts/start.py`。不要修改 `trend-content-factory`。

当前 v0.5.0 已收口为八个入口：总览、持仓工作台、截图导入、投资日报、风险雷达、复盘中心、同步与备份、设置。持仓工作台统一处理详情、快速操作、计划、交易和复盘；快速操作默认只记录，用户明确选择后才更新持仓。

截图导入支持支付宝基金、东方财富和普通 OCR 回退。默认自动识别与解析，但结果必须经过中文确认表人工核对后才能入库。重复持仓按平台加代码或规范化名称覆盖，不能删除历史交易、计划和复盘。风险雷达使用仓位、收益、交易行为、复盘纪律、数据质量五个维度；日报保留风险、建议、计划和待复盘事项；同步与备份页统一管理 JSON 快照、Git 操作和数据库备份。

禁止提交 `data/investment_dashboard.db`、uploads、backups、exports、`.env`、token、日志和真实截图。只有 `data/sync/portfolio_sync.json` 允许提交，它可能包含真实投资数据，因此仓库必须保持 private。文档和测试不得出现用户的具体持仓、真实金额或截图内容。

下一步重点：用脱敏样本增强两类截图 parser，提升来源识别和错误诊断，校准风险与复盘规则，继续隐藏技术字段，并补关键 UI 与数据库迁移测试。接手时先读 `docs/AI_HANDOFF.md`，查看并保留未提交改动，再运行 `python -m pytest`。代码与文档冲突时以当前代码和测试为准。
