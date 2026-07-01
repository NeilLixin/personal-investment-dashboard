# personal-investment-dashboard

一个本地运行的个人投资驾驶舱，用于管理持仓、查看资产配置、控制仓位风险、记录买卖计划与操作日记，并支持支付宝基金/理财/黄金截图的本地 OCR 辅助导入。

它不是自动交易软件，不连接券商下单，不抓取实时行情，不调用 OpenAI API。所有交易决定和数据确认都由用户完成。

## 功能

- 总览：总资产、成本、浮盈亏、收益率、现金比例、待复盘、配置图和风险建议。
- 持仓管理：新增、编辑、删除、筛选、CSV 导入导出、目标区间与风险状态。
- 截图导入：支付宝基金专用坐标 OCR、图片预处理、按行切分、普通 OCR/手动文本兜底、人工编辑确认。
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

v0.4.0 起截图导入默认采用极简流程：上传后自动 OCR、自动判断支付宝基金或东方财富截图、自动解析，
最后统一进入中文确认表格。OCR 原文、预处理图、坐标 items 和解析诊断只在“高级调试模式”中显示。
投资日报已使用中文列名和金额/收益率格式；数据同步页只显示设备状态、三步流程和常用操作；
风险雷达按仓位、收益、交易行为、复盘纪律、数据质量五个维度评分。所有分析仅用于个人记录，
不构成投资建议，也不会自动交易。

安装完成后必须重启 Streamlit。支付宝“基金－我的持有”默认采用“图片预处理 → RapidOCR boxes
坐标 → 三列结构解析 → 人工确认”，不会再只依赖 OCR 原文正则。页面可切换普通 OCR 或手动文本，
并可开启 OCR items 调试表、解析诊断和调试图片保存。即使 OCR 依赖缺失，页面也不会崩溃。

图片预处理会裁掉常见状态栏和底部导航、保留持仓卡片、放大并轻微锐化；按行切分会增加识别时间，
但通常能改善长截图小字。OCR 仍可能把 FOF、符号或金额识别错误，导入前必须逐项核对。

开源项目只作思路参考：[chicang](https://github.com/knrlos/chicang) 的持仓 OCR 导入流程、
[Umi-OCR](https://github.com/hiroi-sora/Umi-OCR) 的离线 OCR 后端形式，以及
[zocr](https://github.com/helloxz/zocr)
的 OCR API 部署形式。当前项目保持 Python + Streamlit + SQLite，不复制 AGPL 源码，也不强依赖这些项目。

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

打开“显示 OCR 调试信息”可查看每个文字块的坐标、名称候选、金额候选、Row 分组、忽略文本和警告。
失败时尽量只截持仓列表，一张图保留 3-6 个持仓，避免压缩或过长截图。支付宝页面格式变化后，
三列阈值和名称规则可能需要调整；无论是否解析成功，金额都必须人工确认。

### 为什么没有实时行情？

v0.1.0 聚焦本地资产记录和仓位纪律，所有数值手动更新或截图导入，避免行情源、授权和错误报价增加复杂度。

### 数据在哪里？

数据库在 `data/investment_dashboard.db`，备份在 `data/backups/`，CSV 在 `data/exports/`。

## 免责声明

这是个人投资记录和辅助决策工具，不构成投资建议，不保证收益，不自动交易。风险提示来自固定本地规则，不能替代独立判断或专业意见。
