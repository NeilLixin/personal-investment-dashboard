# AI Handoff — personal-investment-dashboard

新 ChatGPT / Codex 会话应先阅读本文件，再阅读 `PROJECT_STATE.md`、`ARCHITECTURE.md`、`TASKS.md`、`DECISIONS.md`、`CHANGELOG.md`、`CHATGPT_CONTEXT.md` 和根目录 README。

## 项目定位

这是本地“一人投资驾驶舱”：管理持仓、观察资产配置、约束仓位风险、记录买卖计划与操作复盘。它不是投资建议系统、自动赚钱机器或自动交易程序；不连接券商、不自动买卖、不抓行情、不调用 OpenAI API。

## v0.3.0 已完成

- Streamlit 九页中文界面：总览、持仓、截图导入、计划、日记、复盘、配置、风险和设置。
- SQLite 自动初始化及 holdings、trades、plans、rules、ocr_import_batches、app_settings 表。
- 结构化 JSON 跨设备同步、投资日报、风险评分与复盘统计；旧 trades 表启动时自动迁移。
- 持仓收益、收益率、资产占比和目标区间计算。
- Plotly 资产配置、平台分布、盈亏和集中度图表。
- 本地规则风险雷达。
- RapidOCR 可选集成、OCR boxes 坐标保留和手动 OCR 文本兜底。
- 支付宝基金持仓专用三列解析器、图片预处理、按行切分和失败诊断。
- OCR 结果人工编辑确认及覆盖/新增/跳过策略。
- CSV、SQLite 备份、demo 数据、GitHub 同步脚本与 pytest 测试。

## 目录结构

```text
app.py
src/                 业务、数据库、计算、OCR、解析和 UI 组件
scripts/             demo、备份和 Git 同步
tests/               计算、支付宝解析和规则测试
data/                本地数据库/上传/备份/导出（运行时创建，敏感内容不提交）
docs/                项目维护文档
requirements.txt
requirements-ocr.txt OCR 可选依赖
```

## 关键路径

- 项目：`D:\AAA-Projects\personal-investment-dashboard`
- Windows 虚拟环境：`D:\AAA-Projects\.venvs\personal-investment-dashboard`
- 数据库：`data/investment_dashboard.db`
- Streamlit 入口：`app.py`

## 启动

```powershell
cd D:\AAA-Projects\personal-investment-dashboard
D:\AAA-Projects\.venvs\personal-investment-dashboard\Scripts\Activate.ps1
streamlit run app.py
```

## OCR 方案

`src/ocr_engine.py` 可选加载 `rapidocr-onnxruntime`，Streamlit 进程内只初始化一次。依赖缺失或初始化失败不能阻止应用启动。截图导入始终提供手动文本兜底；OCR 原文会保留在批次记录，解析草稿必须人工确认后才进入 holdings。安装：`pip install -r requirements-ocr.txt`。

支付宝专用链路由 image_preprocess、ocr_engine 和 alipay_fund_parser 组成：先裁剪增强并可选按行切分，
再保留 OCR boxes，最后按名称、金额/昨日收益、持有收益/率三列和 y 坐标分组。失败时回退旧文本解析。

安装后必须重启 Streamlit。页面支持多图逐张识别、自动 OCR 开关、逐图结果与错误；按钮只在没有上传文件时禁用，OCR 依赖缺失时点击按钮会显示安装方式。UploadedFile 读取后会复位到开头，单张坏图不会中断其他图片。

## GitHub 同步

`data/sync/portfolio_sync.json` 是唯一允许提交的运行时数据快照，包含核心投资数据。数据库、uploads、backups、exports、截图、`.env` 与 token 仍禁止提交。私有仓库不得改为 public。

首次上传按 README 执行 `git init` 和 remote 配置。后续使用：

```powershell
python scripts\git_sync.py "update dashboard"
```

脚本不得设置全局代理；只允许用户显式配置 repository-local proxy。

## 禁止提交

- `data/*.db`、`data/uploads/`、`data/backups/`、`data/exports/`
- `.env`、截图原图、真实资产数据、账户信息、Token/API Key/Cookie
- 虚拟环境、缓存和日志

## 重要边界

- 不增加自动交易、券商下单或自动发布交易指令。
- 不增加 OpenAI API 或付费外部 API。
- 第一版不联网抓行情；数据手动录入或截图导入。
- OCR 必须可选，解析结果必须人工确认。
- 风险规则只做提示，不给确定性收益承诺。

## 下一步 TODO

1. 用更多脱敏支付宝截图扩展三列 parser 测试样本和页面变体。
2. 增加更细的 CSV 字段校验和导入错误报告。
3. 真实使用后调整风险阈值和复盘统计。
4. 评估是否增加手动价格快照历史；不要直接跳到行情 API。
5. 增加脱敏 UI 截图和基本 Streamlit smoke test。

## 已知问题

- 支付宝 UI 或列布局变化后坐标 parser 可能需要调整，金额必须人工确认。
- RapidOCR 首次初始化可能较慢，中文识别质量受截图清晰度影响。
- Streamlit 为单机个人工具，没有登录和多用户隔离。
- 风险阈值是通用规则，不代表适合每个人。

## 接手说明

先运行 `pytest`，再启动 Streamlit。修改数据库前保持向后兼容；修改 OCR parser 时必须增加模拟文本测试。不要把真实数据库或截图加入 Git。若代码与文档冲突，以代码和 `PROJECT_STATE.md` 为准，并同步更新本文件。
# v0.4.0 交接补充

- 截图页默认自动 OCR 和自动解析，无法判断类型时在高级模式手动选择。
- 支付宝由 `alipay_fund_parser.py` 解析三列，东方财富由 `eastmoney_parser.py` 解析五列和账户摘要。
- 两种来源统一经过 `parsed_to_drafts` 和中文确认表，绝不直接写库。
- 日报用户可见列名中文化；同步技术信息默认折叠；风险雷达为五维本地规则模型。
- 项目不构成投资建议，不接自动交易。新增截图类型时优先增加独立 parser 和坐标测试。

## v0.5.0 交接补充

- `holdings_page` 是持仓、快速操作、计划、交易、复盘和设置的统一工作台。
- `apply_holding_operation` 是快速操作纯计算边界；每次操作先写 trades，用户明确选择后才更新 holdings。
- `import_service` 以平台+代码或平台+规范化名称匹配，批次重复保留最后一条，覆盖不删除历史表。
- 独立计划、操作、资产配置函数暂保留用于兼容，但已从主导航移除。
- 当前继续使用 Streamlit；React 重写的取舍见 `docs/DECISIONS.md`。
