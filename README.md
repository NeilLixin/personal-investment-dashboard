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
- 截图、数据库、备份、导出文件和 `.env` 均被 `.gitignore` 排除。
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

安装 `requirements-ocr.txt` 后重启 Streamlit。仍失败时可以直接粘贴 OCR 文本，不影响其他功能。

### OCR 解析不准确

RapidOCR 只负责识别文字，支付宝页面格式也会变化。请在确认表格中修正名称、金额、成本、资产类型等字段，再点击确认导入。

### 为什么没有实时行情？

v0.1.0 聚焦本地资产记录和仓位纪律，所有数值手动更新或截图导入，避免行情源、授权和错误报价增加复杂度。

### 数据在哪里？

数据库在 `data/investment_dashboard.db`，备份在 `data/backups/`，CSV 在 `data/exports/`。

## 免责声明

这是个人投资记录和辅助决策工具，不构成投资建议，不保证收益，不自动交易。风险提示来自固定本地规则，不能替代独立判断或专业意见。
