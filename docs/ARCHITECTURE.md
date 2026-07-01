# Architecture

## 技术架构

```text
Streamlit UI (app.py)
  -> sync/report/review services + calculations / rule engine (src/)
  -> SQLite (data/investment_dashboard.db)
  -> Pandas + Plotly for tables/charts
```

Python 业务逻辑不堆在页面：数据库、计算、规则、OCR、支付宝解析、导入和导出分别位于独立模块。

## 数据流

```text
手动录入 / CSV / 截图
  -> 人工检查
  -> holdings / trades / plans
  -> calculations
  -> dashboard / allocation / risk / review
```

## OCR 导入流程

```text
多张截图 -> 原图预览 -> 裁剪/放大/增强 -> 可选按行切分
  -> RapidOCR text + boxes
  -> alipay_fund_parser 按名称/金额/收益三列和 y 行分组
  -> 失败时回退 alipay_parser 纯文本解析
  -> holdings 草稿 -> st.data_editor 人工修改
  -> 重复项选择（覆盖/新增/跳过）
  -> 确认后写入 holdings + 更新 ocr_import_batches
```

OCR 失败是可恢复分支，不允许导致应用启动或截图页面崩溃。
调试信息包含 OCR items 坐标、名称/金额候选、行分组、忽略项和警告；调试图片仅在用户打开开关时
写入被 Git 忽略的 data/exports/ocr_debug/。

## 数据库设计

- `holdings`：资产、成本、市值、收益、目标区间和风险。
- `trades`：操作、原因、情绪、关联计划和复盘。
- `plans`：触发条件、动作、优先级和启停。
- `rules`：可持久化的扩展规则定义。
- `ocr_import_batches`：OCR 原文、解析 JSON 和导入状态。
- `app_settings`：资产配置和本地阈值等 JSON 设置。
- `trades`：新增计划性、复盘状态、结果、标签、经验、信心和纪律字段；自动迁移旧库。

## 跨设备同步

SQLite 始终仅在本地；`sync_service` 将核心表导出为可审查的 `data/sync/portfolio_sync.json`。导入支持 preview、merge、overwrite，写入前自动备份。截图、uploads、backups、exports、`.env` 不进入快照。

## 页面结构

1. 总览 Dashboard
2. 持仓管理
3. 截图导入
4. 买卖计划
5. 操作日记
6. 复盘中心
7. 资产配置
8. 风险雷达
9. 风险雷达
10. 数据同步
11. GitHub 同步
12. 数据备份/设置
# v0.4.0 产品化流程

截图导入采用 `上传 → 本地 OCR boxes → 自动判断支付宝/东方财富 → 对应坐标 parser → 中文确认表 → 人工确认写库`。
调试数据只存在高级模式。`rule_engine` 输出五个风险维度并按维度上限汇总到 0-100 分；不依赖行情、
不预测涨跌、不调用交易接口。同步服务的数据结构保持不变，页面只把路径和 JSON 详情收进高级信息。
