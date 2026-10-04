# 复现与验证

本项目的 Python/SQL 入口已经生成过成功的真实数据运行；固定官方 ZIP 的离线下载 CLI 已运行两次，七个 CSV 均与来源清单哈希一致，翻译文件 BOM 保持。当前文档对照实际命令参数、成功运行记录和模型文件编写。Power BI Desktop 的实机打开、刷新、DAX、保存及导出结果必须以桌面验证记录为准，不能由工程生成或预期数值替代。

2026-10-04 使用真实七表和默认配置，在独立临时输出目录实际执行了本文的 `run.py → build_dashboard.py` 顺序：分析状态为 `passed`、阻断失败为 0、10 个分析 SQL 产生 15 个仓库 CSV；生成器产生 5 个专用 BI CSV、5 条单向关系和 `DataFolder` 参数。正式 raw 和正在验收的看板目录没有被该复现检查覆盖。质量警告仍须查看 `quality.json`，这项命令验证不代表源数据没有缺失，也不代表 Desktop 已验收。

## 环境与固定输入

已记录的本地分析环境为 Windows、PowerShell、Python **3.9.25**、DuckDB **1.4.5**；具体 Python/SQL 用时读取每次成功运行的 `results.json`，不承诺跨机器相同耗时。固定依赖见 [`requirements.txt`](../requirements.txt)，测试及 JSON schema 依赖见 [`requirements-dev.txt`](../requirements-dev.txt)。

原数据来源为 [Olist 官方 Kaggle 数据集](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)，数据许可为 [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)。ZIP 固定 SHA-256：

```text
967e41e04fc306fe604e2a693f488995a8b41e5047418f8a5c8e4abd6deca784
```

原版 ZIP 和七个 CSV 只放本地 `data/raw/`，不上传；金额保持原始单位，币种未核验。哈希不一致时停止，不能自动接受新版或镜像。公开的来源、行数和逐文件哈希见 [`source-provenance.json`](../reports/source-provenance.json)。

## Python/SQL 执行顺序

以下 PowerShell 命令均从仓库根目录运行。已有环境时复用，第一次安装时创建虚拟环境；安装依赖需要网络：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

获取固定官方输入；公开端点未来不可用时，用已经取得且哈希正确的原版 ZIP 离线复用：

```powershell
.\.venv\Scripts\python.exe scripts/download_data.py
# 已有原版 ZIP 时，改用这一条：
.\.venv\Scripts\python.exe scripts/download_data.py --archive data/raw/brazilian-ecommerce.zip
```

下载脚本只用标准库，不读取 Kaggle 凭据。网络失败、源哈希不一致、ZIP 路径不安全、缺必需 CSV 时返回 1，旧 raw 不被候选内容覆盖。原始目录安装的 Windows 重命名边界与恢复方法见 [`data-source.md`](data-source.md)，下载与分析不要同时进行。

检查配置并执行全量分析：

```powershell
.\.venv\Scripts\python.exe scripts/run.py --raw-dir data/raw --output-dir build --config config/analysis.example.yaml
.\.venv\Scripts\python.exe -m pytest -q
```

默认 [`analysis.example.yaml`](../config/analysis.example.yaml)：

```yaml
analysis_start: '2017-02-01'
analysis_end: '2018-07-31'
observation_end: '2018-07-31 23:59:59'
min_state_orders: 100
min_group_orders: 30
```

配置日期为源时间，窗口两端购买日均包含。复购识别历史在报告窗口前也保留，观察截止独立冻结。改变配置后需要重新运行并重新验收；看板生成器当前固定为上述完整月窗口，不能仅修改 YAML 后声称 BI 自动适配另一个窗口。

流程按“原始文件校验→staging→必要质量门禁→事实/维表→模型检查→10条分析SQL→导出→成功指针”执行。`run.py` 成功返回 0 并打印状态、阻断失败数、警告数、SQL 数和耗时；失败返回 2，详细步骤及失败原因保存在本次运行目录。警告不等于源数据毫无异常，要查看其口径和处理。

每次运行写入独立 `build/runs/<run_id>/`，仅通过必要检查后原子更新 `build/current.json`。失败不会替换上一份有效指针，不能把失败候选目录作为正式产物。重新运行同一输入产生新的运行 ID，但不会在上一次金额或订单上累加。

| 文件/目录 | 用途 |
|---|---|
| `build/current.json` | 最新成功运行 ID、配置及来源指纹 |
| `build/runs/<run_id>/source_manifest.json` | 本次导入文件的来源、行数、字段及哈希 |
| `quality.json` | 检查值、error/warning 级别及通过状态 |
| `data_profile.json` | 本次模型画像与覆盖 |
| `warehouse.duckdb` | 本地可查询仓库 |
| `csv/` | 五张模型表及 Q01—Q10 的 15 个 CSV |
| `results.json` | 成功状态、配置、分析输出与真实运行时间 |
| `failed.json` | 失败候选的原因；不代表已发布成功结果 |

这些运行输出包含本地客户/订单标识，默认不公开。安全测试的合成样本与真实数据分开。完整测试是否通过应以本次 `pytest` 退出码为准；不能把旧测试次数当作当前验证证据。

## 生成可编辑 Power BI 工程

从成功指针取得运行目录，再生成两页 PBIP/PBIR 工程和匿名 CSV：

```powershell
$olistRunInfo = Get-Content -Raw -LiteralPath 'build/current.json' | ConvertFrom-Json
$olistRunDir = Join-Path 'build/runs' $olistRunInfo.run_id
.\.venv\Scripts\python.exe scripts/build_dashboard.py --run-dir $olistRunDir --output-dir dashboard
```

公开工程入口为 `dashboard/Olist.pbip`；`dashboard/data/` 为本机刷新输入。当前 Power Query 数据文件夹参数的真实名称是 **`DataFolder`**，不是 `PowerBIDataFolder`；它代表本机 Power BI 数据文件夹，仓库保存可移植占位路径，不写个人机器路径。用户在本地设置到 `dashboard/data` 的绝对路径后才可刷新。

生成器还有 `--data-folder`，可用于不公开的本地验证工程；传入的真实路径会写入模型，发布工程不使用此选项。公开前检查模型、缓存、PBIX、截图和 PDF 中的数据源路径与其他个人信息。

下面是后续可选的 Desktop 验证顺序：打开 PBIP，设置 `DataFolder`，刷新，检查两页日期/州筛选和品类交互，运行三组 DAX 对账，再另存 PBIX、截图及导出 PDF。实际验证范围见 [`validation.md`](validation.md)。

## SQL/Power BI 对账

生成器提供全窗口、2017 年 2 月、SP 州三组同口径文件：

- `dashboard/reconciliation/all.sql` 与 `all.dax`。
- `dashboard/reconciliation/month_2017_02.sql` 与 `month_2017_02.dax`。
- `dashboard/reconciliation/state_SP.sql` 与 `state_SP.dax`。

`expected.json` 是匿名 CSV 独立计算的预期结果，`sql-verified.json` 如存在则记录 SQL 核验；二者都不能证明实际 DAX 已执行。后续若验证 DAX，需要在刷新后的 Desktop 模型执行，并记录实际值。订单数、指标分子/分母必须一致，金额误差不超过 0.01 原始单位；覆盖、比例和客单价按分子/分母重新计算。DAX 使用的日期、州与 SQL 必须相同。

检查“品类点击不影响订单级卡片”“缺日期不显示准时”“零分母为空值”，并在工具提示或表格查看样本数。JSON schema 测试确认工程格式，不能替代 Desktop 的刷新和视觉验收。有关工程字段、参数和实际验证记录入口见 [`dashboard/POWERBI.md`](../dashboard/POWERBI.md)。
