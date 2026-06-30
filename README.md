# personal-investment-dashboard

一个本地运行的个人投资驾驶舱，用于管理持仓、查看资产配置、控制仓位风险、记录买卖计划与操作日记，并支持支付宝基金/理财/黄金截图的本地 OCR 辅助导入。

它不是自动交易软件，不连接券商下单，不抓取实时行情，不调用 OpenAI API。所有交易决定和数据确认都由用户完成。

## 功能

- 总览：总资产、成本、浮盈亏、收益率、现金比例、待复盘、配置图和风险建议。
- 持仓管理：新增、编辑、删除、筛选、CSV 导入导出、目标区间与风险状态。
- 截图导入：多图预览、本地 OCR、手动文本兜底、支付宝解析、人工编辑确认、重复项策略。
- 买卖计划：补仓、减仓、止盈、止损、定投和观察计划。
- 操作日记与复盘中心：交易原因、情绪、计划关联和到期复盘。
- 资产配置：当前比例与目标区间对比。
- 风险雷达：现金、集中度、高风险仓位、黄金/科技仓位、浮亏和操作频率规则。
- 数据备份：CSV 压缩包和完整 SQLite 备份。
- 数据同步：把核心表导出为 `data/sync/portfolio_sync.json`，用于私有 GitHub 跨设备同步。
- 投资日报：汇总资产、风险、计划和复盘提醒，可保存或下载 Markdown。
- 风险与复盘：0-100 风险分、可调阈值、月度/情绪/标签统计图表。

## 功能截图说明

> 截图占位：可在长期使用后将脱敏后的总览、持仓管理、截图确认和风险雷达页面截图放入 `docs/images/`。不要提交真实资产截图。

## Windows 安装

```powershell
cd D:\AAA-Projects
python -m venv D:\AAA-Projects\.venvs\personal-investment-dashboard
D:\AAA-Projects\.venvs\personal-investment-dashboard\Scripts\Activate.ps1
cd D:\AAA-Projects\personal-investment-dashboard
pip install -r requirements.txt
streamlit run app.py
```

浏览器通常自动打开 `http://localhost:8501`。

## OCR（可选）

基础依赖不包含 OCR，因此 OCR 安装失败也不会影响页面启动。需要本地中文截图识别时执行：

```powershell
pip install -r requirements-ocr.txt
```

等价命令：

```powershell
pip install rapidocr-onnxruntime
```

OCR 不可用时，截图导入页会显示原因，并提供“手动粘贴 OCR 文本”。OCR 解析结果不会直接入库，必须先在确认表格中人工检查。

安装完成后必须重启 Streamlit。截图导入支持多图预览、逐张 OCR、可选的“上传后自动 OCR”和逐图错误提示；自动 OCR 默认关闭。即使 OCR 依赖缺失，上传图片后按钮仍可点击，并会显示安装命令，不会让页面崩溃。

## Demo 数据与测试

```powershell
python scripts\seed_demo_data.py
pytest
```

重置为 demo 数据会清空当前本地数据库：

```powershell
python scripts\reset_demo_data.py --yes
```

导出 SQLite 备份和 CSV 压缩包：

```powershell
python scripts\export_backup.py
```

## 数据安全

- 默认数据库：`data/investment_dashboard.db`。
- 仅 `data/sync/portfolio_sync.json` 会作为结构化快照提交；它包含真实投资数据。
- 截图、SQLite 数据库、备份、导出文件、上传文件和 `.env` 均被 `.gitignore` 排除。
- 私有仓库不等于绝对安全，禁止把仓库设为 public，禁止提交 token、截图或 `.env`。
- 不要提交真实资产数据、账户信息、截图原图、API Key 或 Cookie。
- 页面只在本机使用，不建议暴露到公网。

## GitHub 首次上传

```powershell
git init
git add .
git commit -m "init personal investment dashboard"
git branch -M main
git remote add origin <你的GitHub仓库地址>
git push -u origin main
```

## Mac / Windows 跨设备同步

Mac：`git pull` → `python scripts/start.py` → 页面修改数据 → “数据同步”导出 → “GitHub 同步”提交推送。

Windows：`git pull` → `python scripts\start.py` → “数据同步”预览 → 选择合并或覆盖并确认导入。反向同步步骤相同。覆盖和合并导入前都会自动备份本地数据库。

投资日报页点击“生成日报”，可复制、下载或保存 Markdown；风险雷达页可维护基础阈值；复盘中心可快速填写结果并查看统计图表。

后续同步：

```powershell
python scripts\git_sync.py "update dashboard"
```

同步脚本不会修改全局代理。确实需要代理时，只配置当前仓库：

```powershell
git config --local http.proxy http://127.0.0.1:7897
git config --local https.proxy http://127.0.0.1:7897
```

## 常见问题

### 页面能开，但 OCR 不可用

确认已激活当前项目虚拟环境，再执行 `pip install -r requirements-ocr.txt`，然后彻底停止并重启 Streamlit。页面会区分“依赖不可用”和“初始化失败”，并显示底层错误。仍失败时可使用 iPhone/支付宝的文字识别，把结果粘贴到 OCR 原文区域，不影响后续人工确认导入。

如果图片已上传但无法识别，请检查文件是否为 PNG/JPG/JPEG/WebP、图片是否损坏，以及终端启动 Streamlit 的 Python 是否就是安装 OCR 依赖的虚拟环境。

### OCR 解析不准确

RapidOCR 只负责识别文字，支付宝页面格式也会变化。请在确认表格中修正名称、金额、成本、资产类型等字段，再点击确认导入。

### 为什么没有实时行情？

v0.1.0 聚焦本地资产记录和仓位纪律，所有数值手动更新或截图导入，避免行情源、授权和错误报价增加复杂度。

### 数据在哪里？

数据库在 `data/investment_dashboard.db`，备份在 `data/backups/`，CSV 在 `data/exports/`。

## 免责声明

这是个人投资记录和辅助决策工具，不构成投资建议，不保证收益，不自动交易。风险提示来自固定本地规则，不能替代独立判断或专业意见。
