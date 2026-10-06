# Olist 经营与履约分析

中文简介：可复现的 Olist 经营与履约分析，交付真实使用的两页 Power BI 工程。统一主题、可读图表字号、键盘顺序和同步筛选，保留数据模型、指标口径与来源署名。

English summary: Reproducible Olist commerce and delivery analysis with an editable two-page Power BI project, a registered visual theme, readable chart labels, ordered keyboard navigation and synchronized filters.

### 用 SQL 和 Power BI 串起业务问题、指标与分析证据

**基于 Olist 公开历史数据，通过 10 组 SQL 分析研究经营趋势、履约表现与 30 天复购，提供明确指标、质量检查和可编辑的双页 Power BI 工程。** 结论描述观测到的规律与关联。

[English](README.md) | 中文

[快速开始](#快速开始) · [分析结论](reports/analysis-summary.md) · [指标口径](docs/metrics.md) · [复现说明](docs/reproduce.md)

![月度商品金额与已交付订单数](reports/images/commerce-trend.png)

*由 SQL 分析输出生成的月度经营图，金额为原始数据单位。*

## 已实现内容

- 7张源表清洗、订单与明细独立事实表、日期和客户州共用维表；品类仅影响明细金额。
- Q01—Q10：经营趋势、订单数优先的订单数与客单价顺序分解、品类和州贡献、配送时长、月份与州分层评价对照、30天观测复购 cohort。
- 关键质量检查阻止失败结果发布；每次全量重建，失败运行保留上一份成功结果。
- 删除不必要标识的看板数据、明确分母的 DAX、通过微软公开 JSON Schema 校验的 PBIP/PBIR 工程。
- 离线业务样本测试、固定官方数据 SHA-256 的下载脚本和复现文档。

**验证结果：** 离线业务测试、SQL 必要质量门禁、导出金额对账和微软 PBIR JSON Schema 校验已通过。Desktop 刷新、实际 DAX 对账与 PBIX/PDF 导出仍待完成。详见[验证记录](docs/validation.md)。

## 实际数据与结果

官方源数据含99,441条订单和112,650条明细。经过时间覆盖检查，主分析窗口选为 **2017-02-01至2018-07-31**，共18个日历月。

| 指标 | 完整分析窗口 |
|---|---:|
| 最终状态为已交付的订单 | 89,110单 |
| 已交付商品金额，不含运费 | 12,230,652.13原始单位 |
| 商品客单价 | 137.25原始单位 |
| 延迟订单／配送日期有效订单 | 6,116／89,102，6.86% |
| 评分有效订单／已交付订单 | 88,497／89,110，99.31% |

金额衡量不含运费的已交付商品价值；收入与利润分析需要额外会计数据。当前核验的官方元数据未直接确认币种，因此展示为原始数据单位。退款率与转化漏斗分析所需的退款流水和访问曝光数据未包含在源数据中。详细证据、评价时序敏感性和复购观察限制见[一页分析结论](reports/analysis-summary.md)。

## 快速开始

需要 Python 3.9+、[uv](https://docs.astral.sh/uv/)；后续可选的交互验收需64位 Power BI Desktop。在仓库根目录执行：

```sh
uv venv --python 3.9
uv pip install --python .venv -r requirements-dev.txt
uv run --no-project --python .venv python scripts/download_data.py
uv run --no-project --python .venv python scripts/run.py
```

官方下载文件必须匹配固定 SHA-256。若 Kaggle 更新了文件，应重新核验来源与口径，再更新版本。已有 ZIP 可使用 `--archive /path/to/brazilian-ecommerce.zip` 离线导入。

`build/current.json` 记录最近一次成功运行。读取其中的 `run_id`，替换下列占位符：

```sh
uv run --no-project --python .venv python scripts/build_reports.py --run-dir build/runs/<run_id> --output-dir reports
uv run --no-project --python .venv python scripts/build_dashboard.py --run-dir build/runs/<run_id> --output-dir dashboard
uv run --no-project --python .venv python -m pytest -q
```

若后续进行 Desktop 验证，可打开 `dashboard/Olist.pbip`，将 **DataFolder** 设置为本机 `dashboard/data` 的绝对路径后刷新。[复现说明](docs/reproduce.md)提供平台命令、看板交互和可选 DAX 对账步骤。

## 作品证据

| 材料 | 展示内容 |
|---|---|
| [分析结论](reports/analysis-summary.md) | 观察、证据、调查建议与不能推出的结论 |
| [指标字典](docs/metrics.md) | 粒度、分子分母、时间与缺失规则 |
| [数据模型](docs/data-model.md) | 两事实表、维表和筛选方向 |
| [分析 SQL](sql/analysis) | Q01—Q10及窗口函数、分层、cohort |
| [质量报告](reports/quality-report.md) | 真实质量问题、阻断项与运行时间 |
| [30天复购附表](reports/cohort-30d.csv) | 成熟分母与观察覆盖 |
| [三组对账](dashboard/reconciliation) | SQL、DAX和独立期望值 |
| [人工计算](tests/fixtures/manual_checks.md) | 可手算的 Q02／Q07／Q10样例 |
| [面试讲解](docs/interview-guide.md) | 自己理解、复现后再使用简历表述 |

Q09客户级结果和数据库仅保存在本机。公开看板数据删除了客户、订单、商品标识及评价原文。

## 来源与使用条件

来源：[Olist 巴西电商公开数据集](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)。派生数据材料保留 **CC BY-NC-SA 4.0** 的署名、非商业使用和相同方式共享要求。微软 JSON Schema 保留原 MIT 许可。原创代码版权归 cloudwallker，尚未指定单独的代码复用许可。详见[署名说明](NOTICE.md)与[数据来源](docs/data-source.md)。
