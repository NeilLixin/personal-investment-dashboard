# Mac mini 迁移与本地部署说明

## 1. 适用范围

本文只适用于把 `personal-investment-dashboard` 从一台 Mac 迁移到 Mac mini，并在 Mac mini 上重建本地运行环境。

本文不覆盖 Windows、服务器部署、Docker 部署或公开生产环境。

## 2. 迁移原则

可以迁移：

- 项目代码，以及 `docs/`、`src/`、`tests/`、`scripts/`
- `requirements.txt`、`requirements-ocr.txt`、`README.md`
- 已脱敏的 demo 数据
- 用户明确需要保留的本地 SQLite 数据库
- 用户明确需要保留的结构化同步 JSON

不应迁移：

- `.venv/`、`venv/` 和旧 Mac 上的 `site-packages`
- 旧 Mac 的 Python 安装目录
- `__pycache__/`、`.pytest_cache/`、`.mypy_cache/`、`.ruff_cache/`
- 临时日志和本地缓存

禁止提交或公开：

- `.env`、token、API key 或代理凭据
- 真实截图、真实资产导出和任何含真实账户、持仓或金额的文件
- SQLite 数据库及其旁路文件
- `data/uploads/`、`data/backups/`、`data/exports/`

虚拟环境必须在 Mac mini 上重新创建，依赖必须通过项目的 requirements 文件重新安装。不要跨机器复制旧虚拟环境。

## 3. 推荐目录结构

项目目录：

```text
/Users/lixin/personal-investment-dashboard
```

虚拟环境：

```text
/Users/lixin/.venvs/personal-investment-dashboard
```

将虚拟环境放在项目目录之外，可降低误复制、误提交和路径耦合的风险。

## 4. Mac mini 基础环境准备

安装 Homebrew：

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Apple Silicon Mac mini 通常需要把 Homebrew 加入 shell 环境：

```bash
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
eval "$(/opt/homebrew/bin/brew shellenv)"
brew --version
```

安装并验证 Python 3.11：

```bash
brew install python@3.11
python3.11 --version
```

安装并验证 Git：

```bash
brew install git
git --version
```

## 5. 获取项目代码

方式一：从私有 Git 仓库 clone（推荐）。

```bash
cd /Users/lixin
git clone <private-repo-url> personal-investment-dashboard
```

不要把仓库改为公开仓库，也不要把访问凭据直接写进命令脚本或文档。

方式二：从旧 Mac 复制项目目录。复制前排除 `.venv/`、`venv/`、`__pycache__/`、测试缓存、日志、临时缓存和敏感文件。真实数据仅在用户明确需要时通过安全的本地传输方式单独迁移。

## 6. 创建虚拟环境

```bash
cd /Users/lixin/personal-investment-dashboard
mkdir -p /Users/lixin/.venvs
python3.11 -m venv /Users/lixin/.venvs/personal-investment-dashboard
source /Users/lixin/.venvs/personal-investment-dashboard/bin/activate
python --version
python -m pip --version
python -m pip install --upgrade pip setuptools wheel
```

`python --version` 应显示 Python 3.11，并且 pip 路径应位于上述虚拟环境中。

## 7. 安装基础依赖

当前项目使用 `requirements.txt`，没有 `requirements-dev.txt` 或 `pyproject.toml` 安装流程：

```bash
cd /Users/lixin/personal-investment-dashboard
source /Users/lixin/.venvs/personal-investment-dashboard/bin/activate
python -m pip install -r requirements.txt
```

基础依赖包含 Streamlit、Pandas、Plotly、Pillow、python-dotenv 和 pytest。

## 8. 安装 OCR 可选依赖

RapidOCR 只用于本地截图识别，是可选依赖：

```bash
python -m pip install -r requirements-ocr.txt
python -c "from rapidocr_onnxruntime import RapidOCR; print('RapidOCR OK')"
```

OCR 安装失败不应影响主体启动，截图导入仍可使用手动粘贴文本的兜底流程。安装成功后需要彻底停止并重新启动 Streamlit。

## 9. 安装市场数据可选依赖

项目的市场快照和基金代码候选库可选使用 AKShare：

```bash
python -m pip install akshare
python -c "import akshare as ak; print('akshare ok', ak.__version__)"
```

未安装 AKShare 时，联网市场快照更新和候选库刷新不可用，但项目主体应能启动，并可继续使用截图或手动文本。安装成功后需要重启 Streamlit。AKShare 接口还可能受网络、上游接口变化和基金代码完整性影响。

## 10. 本地数据迁移

本项目的重要本地数据包括：

```text
data/investment_dashboard.db
data/sync/portfolio_sync.json
```

可能含真实敏感数据的目录包括：

```text
data/uploads/
data/backups/
data/exports/
```

- 若要完整保留旧 Mac 的本地状态，在项目停止运行后，将 `data/investment_dashboard.db` 安全复制到 Mac mini 的相同相对路径。复制前建议保留独立备份。
- 若只需借助私有 Git 仓库同步结构化数据，可使用 `data/sync/portfolio_sync.json`，再通过应用的“同步与备份”页面预览和导入。
- 导入结构化快照前应用会备份数据库；覆盖模式仍须人工确认。
- 数据库、真实截图、上传文件和真实导出文件不得提交到仓库。私有仓库也不是绝对安全，结构化同步文件可能包含真实持仓，必须谨慎控制访问权限。
- 如需迁移 `.env`，应在 Mac mini 上根据个人环境手动重建，不通过 Git 或文档传递值。

迁移数据库前先关闭旧 Mac 和 Mac mini 上正在使用该数据库的应用。迁移后如果数据异常，先检查路径和备份，不要直接运行重置 demo 数据的脚本。

## 11. 启动项目

项目的推荐启动入口为：

```bash
cd /Users/lixin/personal-investment-dashboard
source /Users/lixin/.venvs/personal-investment-dashboard/bin/activate
python scripts/start.py
```

该脚本会在项目根目录运行 Streamlit 的 `app.py`。也可以直接执行：

```bash
python -m streamlit run app.py
```

## 12. 运行测试

```bash
cd /Users/lixin/personal-investment-dashboard
source /Users/lixin/.venvs/personal-investment-dashboard/bin/activate
python -m pytest
```

测试失败时先确认当前 Python、虚拟环境和依赖，再根据首个具体错误排查。不要为了让测试通过而覆盖真实数据库或修改业务数据。

## 13. 项目专项验证

以下脚本当前存在，但会访问网络、读取本地持仓或刷新本地候选缓存，应在理解影响并确认数据环境后按需运行，不是基础迁移的强制步骤：

```bash
python scripts/test_market_data_fetch.py
python scripts/refresh_fund_code_candidates.py
python scripts/inspect_holdings_for_market_snapshot.py
```

还可按需使用只读基金代码匹配脚本：

```bash
python scripts/match_missing_fund_codes.py
```

完成基础测试后进行人工检查：

- 打开总览页，确认指标和图表正常。
- 打开持仓工作台，确认筛选、详情、计划、交易和设置可访问。
- 用脱敏样本检查截图导入、人工确认表和 OCR 状态；不要让 OCR 结果未经确认写库。
- 检查市场快照能否识别 AKShare；无代码、网络失败和依赖缺失应显示明确诊断。
- 检查投资日报能够生成，表格列名为中文。
- 检查风险雷达能够加载且不报错；它只依据本地数据提示风险，不预测行情。
- 检查“同步与备份”中的预览、备份提示和高级信息。

## 14. pip 下载慢或失败

网络较慢时可选择镜像并延长超时：

```bash
python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --timeout 120 --retries 10
python -m pip install akshare -i https://pypi.tuna.tsinghua.edu.cn/simple --timeout 120 --retries 10
python -m pip install -r requirements-ocr.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --timeout 120 --retries 10
```

若仍失败，优先检查网络和本机代理环境变量。不要把代理账号、token、密码或完整代理地址写入文档、脚本或仓库。

## 15. 常见问题排查

### `python` 命令找不到或版本不对

先使用 `python3.11`，确认 Homebrew 的 Python 3.11 已安装，再激活项目虚拟环境。可用 `which python` 检查当前解释器路径。

### `streamlit` 找不到

确认已经激活 `/Users/lixin/.venvs/personal-investment-dashboard`，并在该环境中安装了 `requirements.txt`。优先使用 `python -m streamlit` 避免命令路径混淆。

### OCR 不可用

安装 `requirements-ocr.txt`，运行 RapidOCR 验证命令，然后彻底重启项目。若仍失败，查看页面给出的“依赖不可用”或“初始化失败”诊断，并暂时使用手动文本流程。

### AKShare 不可用

安装并验证 AKShare 后重启项目。若 import 成功但刷新失败，检查网络、上游接口和持仓的 6 位代码；失败应逐只隔离，不应阻止其他页面使用。

### 启动后找不到本地数据

检查 `data/` 是否位于项目根目录、数据库是否为 `data/investment_dashboard.db`，以及复制后的文件权限。结构化同步文件不能自动替代 SQLite，必须在页面中预览并导入。

### 迁移后测试失败

确认 Python 为 3.11、虚拟环境路径正确、基础依赖完整，再查看第一个具体报错。不要直接覆盖数据库，也不要运行 `scripts/reset_demo_data.py` 或 `scripts/seed_demo_data.py` 处理真实数据环境。

## 16. 迁移后的检查清单

- [ ] Homebrew 已安装
- [ ] Python 3.11 已安装
- [ ] Git 已安装
- [ ] 项目代码已 clone 或复制
- [ ] 虚拟环境已创建
- [ ] 虚拟环境已激活
- [ ] `requirements.txt` 已安装
- [ ] 可选 OCR 依赖已安装（如需要）
- [ ] 可选 AKShare 已安装（如需要）
- [ ] 本地数据库或同步文件已安全迁移（如需要）
- [ ] `.env` 已按需在本机重建，但未提交
- [ ] 项目能够启动
- [ ] `python -m pytest` 通过
- [ ] 总览、持仓工作台、截图导入、投资日报、风险雷达和同步功能验证通过

## 17. 当前项目的特殊注意事项

- 这是单人本地工具，不应部署为公网服务。
- OCR 导入始终需要人工检查和确认，不能自动写入真实持仓。
- 市场快照不会修改 holdings、交易、计划或复盘；AKShare 只是可选数据源。
- 市场 API 依赖有效的 6 位代码；基金代码补全必须经过确认，歧义项不能静默写库。
- SQLite 是本地主数据；Git 同步使用结构化 JSON，不跨设备同步 SQLite 二进制文件。
- 远端空代码不会清除本地已有代码，非空冲突保留本地并报告诊断。
- 不要把真实数据库、截图、上传、导出、token 或账户数据提交到仓库。

