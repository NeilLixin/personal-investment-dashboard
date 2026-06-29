# Architecture

## 技术架构

```text
Streamlit UI (app.py)
  -> services / calculations / rule engine (src/)
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
多张截图 -> 图片预览 -> RapidOCR（可选）或手动文本
  -> 保留 OCR 原文 -> alipay_parser
  -> holdings 草稿 -> st.data_editor 人工修改
  -> 重复项选择（覆盖/新增/跳过）
  -> 确认后写入 holdings + 更新 ocr_import_batches
```

OCR 失败是可恢复分支，不允许导致应用启动或截图页面崩溃。

## 数据库设计

- `holdings`：资产、成本、市值、收益、目标区间和风险。
- `trades`：操作、原因、情绪、关联计划和复盘。
- `plans`：触发条件、动作、优先级和启停。
- `rules`：可持久化的扩展规则定义。
- `ocr_import_batches`：OCR 原文、解析 JSON 和导入状态。
- `app_settings`：资产配置和本地阈值等 JSON 设置。

## 页面结构

1. 总览 Dashboard
2. 持仓管理
3. 截图导入
4. 买卖计划
5. 操作日记
6. 复盘中心
7. 资产配置
8. 风险雷达
9. 数据备份/设置
