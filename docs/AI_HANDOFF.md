# personal-investment-dashboard 项目交接文档

## 1. 项目定位

这是一个本地运行的个人投资辅助系统，中文名为“投资驾驶舱”。核心用途是管理持仓、通过截图辅助录入、记录交易与计划、完成复盘、生成投资日报、提示仓位与行为风险，并在 Mac 和 Windows 之间同步结构化数据。

它不是自动交易软件：不接券商下单接口，不自动买卖，不预测涨跌，不保证收益，也不构成投资建议。

## 2. 技术栈

- Python 3.11、Streamlit、SQLite
- Pandas、Plotly、Pillow
- RapidOCR / `rapidocr-onnxruntime`（可选依赖）
- pytest

当前没有使用 Vue、React、原生 JavaScript 或 FastAPI。现阶段继续用 Streamlit 做产品化与稳定性优化；等功能、数据模型和使用流程稳定后，再评估 React/Vue + FastAPI。

## 3. 运行路径

Mac：

```bash
cd /Users/lixin/personal-investment-dashboard
source /Users/lixin/.venvs/personal-investment-dashboard/bin/activate
python scripts/start.py
```

Windows：

```powershell
cd D:\AAA-Projects\personal-investment-dashboard
D:\AAA-Projects\.venvs\personal-investment-dashboard\Scripts\Activate.ps1
python scripts\start.py
```

不要修改另一个旧项目：`/Users/lixin/trend-content-factory` 或 `D:\AAA-Projects\trend-content-factory`。

## 4. 数据和隐私

本地数据库是 `data/investment_dashboard.db`。

禁止提交：SQLite 数据库及旁路文件、`data/uploads/`、`data/backups/`、`data/exports/`、`.env`、token、日志、真实截图、账户信息和真实资产导出文件。

允许提交：`data/sync/portfolio_sync.json`。它用于私有 GitHub 仓库中的跨设备结构化数据同步，可能包含真实持仓数据。私有仓库不等于绝对安全，禁止把仓库设为 public。

文档、测试和 demo 数据中不得出现用户的具体持仓名称、真实金额或真实截图内容。

## 5. 当前主要模块

- `app.py`：Streamlit 入口、八个主导航和页面编排
- `src/database.py`：SQLite 初始化、查询和兼容迁移
- `src/calculations.py`：收益、占比和配置状态计算
- `src/ocr_engine.py`、`src/image_preprocess.py`：本地 OCR、坐标结果归一化和图片预处理
- `src/alipay_fund_parser.py`、`src/eastmoney_parser.py`：不同截图来源的坐标解析
- `src/alipay_parser.py`：普通 OCR 文本回退解析
- `src/import_service.py`：确认导入、批次去重和覆盖更新
- `src/rule_engine.py`：五维风险评分和规则建议
- `src/report_service.py`：投资日报和 Markdown
- `src/market_data_service.py`：可选市场接口、刷新间隔、快照保存与读取
- `src/profit_screenshot_parser.py`：第三方 App 今日收益文本解析和持仓匹配
- `src/review_service.py`：复盘统计与洞察
- `src/sync_service.py`、`src/git_service.py`：结构化同步、备份和 Git 状态
- `src/ui_components.py`：通用 UI、中文列名与格式化组件

实际代码优先于文档；新增职责应继续拆到 `src/`，不要把业务逻辑堆回页面函数。

## 6. 当前产品方向

v0.7.0 已完成产品化收口、市场快照刷新诊断与基金代码补全助手，主导航仍为：总览、持仓工作台、截图导入、投资日报、风险雷达、复盘中心、同步与备份、设置。

计划、交易记录和持仓设置已经并入持仓工作台；资产配置融入总览与风险判断；数据同步、GitHub 操作和备份已经合并。下一阶段重点是稳定真实使用流程、减少技术感、改善空状态与错误提示，而不是继续增加页面。

## 7. 持仓工作台

持仓工作台是日常操作中心，负责持仓筛选、详情、快速操作、买卖计划、交易记录、复盘和持仓设置。

快速操作默认“仅记录操作”；只有用户明确选择“记录并更新持仓”时，才修改市值、成本或份额。每次操作先写交易记录，历史计划、交易和复盘不得因持仓覆盖导入而被删除。

## 8. 截图导入

默认流程是：上传截图 → 自动 OCR → 自动判断来源 → 自动解析 → 中文确认表 → 用户确认后入库。

当前支持支付宝基金持仓、东方财富持仓和普通 OCR 文本回退。OCR 原文、坐标项、预处理图、诊断 JSON 和路径默认隐藏，只在高级调试模式显示。OCR 结果永远不能直接写入持仓，金额和名称必须人工确认。

## 9. 重复持仓规则

截图导入默认覆盖同平台已有持仓，而不是新增重复行：

- code 非空：`platform + code`
- code 为空：`platform + normalized_name`

规范化名称会清理空白、换行、括号差异和无关标签。同一批次重复时保留最后一次结果。覆盖只更新持仓核心字段，不删除历史交易、计划或复盘。

## 10. 风险雷达

风险雷达不预测市场，只根据本地数据评估五个维度：仓位风险、收益风险、交易行为风险、复盘纪律风险、数据质量风险。

输出包括 0–100 总风险分、正常/注意/危险等级、重要风险项、具体依据和行动建议。建议必须说明触发依据，不能只显示笼统的“危险”。

## 11. 投资日报

日报默认展示今日总览、配置摘要、风险提示、今日建议、待复盘事项和计划提醒。用户界面的表格列名必须中文化，不直接暴露数据库字段。

Markdown 保留在“导出 / 复制日报”折叠区域，可用于备忘录、Obsidian、Notion 或外部复盘；仅在本工具查看时可忽略。

## 12. 同步与备份

“同步与备份”统一承载结构化数据导出/导入、Git 拉取/推送、数据库备份和备份查看。默认只显示设备、数据状态、最近同步与备份时间及常用操作。

数据库路径、同步文件路径、remote、分支、hostname、JSON 数量和 Git 原始状态放在高级信息中。导入前必须备份；覆盖模式必须明确确认。

### 市场快照 / 今日收益

`src/market_data_service.py` 管理独立快照与刷新日志；页面只在加载时检查数据库时间，默认超过 60 分钟提示刷新，不运行后台任务。AKShare 是可选依赖，失败必须逐只隔离。`src/profit_screenshot_parser.py` 解析第三方 App 收益文本，确认后只写快照，不修改 holdings、交易、计划或复盘。场外基金必须区分官方净值、待净值更新和第三方估算。

API 刷新依赖有效的 6 位代码：交易所 ETF 前缀优先走 ETF 接口，其余代码优先走开放式基金接口并允许备用接口。无代码、现金和无代码黄金才会 skipped；AKShare 缺失或网络异常必须记为 failed。刷新结果始终包含逐条成功、失败、跳过原因，页面高级诊断和 `market_refresh_logs` 可查看。终端诊断使用 `scripts/test_market_data_fetch.py` 与 `scripts/inspect_holdings_for_market_snapshot.py`。

`src/fund_code_service.py` 从多个 AKShare 基金接口维护按日缓存的候选库，并按名称保守推荐代码。任何写入都必须经过确认表；截断名称、A/C 类别歧义、多候选和低置信结果不得自动勾选。同步快照保留 `holdings.code`，远端空值不得清除本地代码，非空冲突保留本地并报告诊断。候选刷新和只读匹配脚本分别为 `scripts/refresh_fund_code_candidates.py`、`scripts/match_missing_fund_codes.py`。

## 13. UI 方向

继续用 Streamlit 的 CSS、卡片、tabs、expander、`st.data_editor` 和 `column_config` 提升产品感。金额、收益率、风险颜色和中文列名应保持一致。

普通界面默认隐藏 id、时间戳、raw text、parsed JSON、schema version、数据库路径和 debug 信息，并提供友好的空状态与可执行错误提示。

## 14. OCR 安装

Mac：

```bash
cd /Users/lixin/personal-investment-dashboard
source /Users/lixin/.venvs/personal-investment-dashboard/bin/activate
python -m pip install -r requirements-ocr.txt
python -c "from rapidocr_onnxruntime import RapidOCR; print('RapidOCR OK')"
```

Windows：

```powershell
cd D:\AAA-Projects\personal-investment-dashboard
D:\AAA-Projects\.venvs\personal-investment-dashboard\Scripts\Activate.ps1
python -m pip install -r requirements-ocr.txt
python -c "from rapidocr_onnxruntime import RapidOCR; print('RapidOCR OK')"
```

安装后必须重启 Streamlit。OCR 缺失或初始化失败时页面仍应可用，并保留手动粘贴文本的兜底。如果安装遇到 SOCKS 代理错误，检查或临时清理代理环境变量，禁止把代理凭据写入仓库。

## 15. GitHub 注意事项

仓库是私有仓库。push 出现 403 时，检查 fine-grained token 是否选择本仓库，并具有 Contents Read and write、Metadata Read-only 权限。禁止把 token 写入代码、文档、命令脚本或提交记录。

## 16. 下一步优先任务

产品化导航与市场快照已在 v0.6.0 完成。接下来优先：

1. 用脱敏样本补齐支付宝和东方财富页面变体测试。
2. 提升截图来源识别、坐标解析和错误诊断的稳定性。
3. 真实使用后校准五维风险阈值和复盘洞察。
4. 继续简化持仓工作台与同步页，隐藏非必要技术信息。
5. 增加关键 Streamlit 流程 smoke test 和数据库迁移测试。
6. 评估手动价格快照历史；不要直接接行情或自动交易。

## 17. 测试

每次改动后运行：

```bash
python -m pytest
```

重点覆盖支付宝/东方财富解析、重复覆盖、快速操作、风险评分、日报中文化、同步导入导出、OCR 不可用降级、数据库迁移和空数据库。

## 18. 重要原则

- 不自动交易，不预测涨跌，不构成投资建议。
- OCR 导入必须人工确认。
- 不提交真实截图、SQLite、`.env`、token 或真实资产导出。
- 当前不使用 React 重写，优先简化日常流程。
- 前台隐藏技术细节，代码保持模块化，文档随行为变更。

接手顺序：先读本文件与 `PROJECT_STATE.md`，查看 `git status` 并保留用户未提交改动；运行测试后再修改。代码与文档冲突时，以当前代码和测试为准，并同步修正文档。
