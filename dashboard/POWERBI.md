# Power BI 工程 / Power BI project

`Olist.pbip` 是可编辑工程入口；`Olist.Report/definition/` 保存两页 PBIR 报表，`Olist.SemanticModel/model.bim` 保存 TMSL 语义模型。工程格式已做微软 schema 校验；本次交付不包含 Desktop 刷新、实际 DAX 对账、PBIX 和 PDF。后续进行这部分可选验证时，需要由 Desktop 打开、刷新并保存真实结果。验证范围见 [`docs/validation.md`](../docs/validation.md)。

## 生成与打开

先运行项目数据流程，选择通过质量检查的 `run_dir`，再运行：

```powershell
python scripts/build_dashboard.py --run-dir <已通过检查的运行目录> --output-dir dashboard
```

在 Power BI Desktop 中打开 `dashboard/Olist.pbip`。首次使用时，在“转换数据 → 编辑参数”中将 `DataFolder` 设置为本机 `dashboard/data` 的绝对路径，然后刷新。仓库工程使用公开占位路径；实际保存 PBIX 后仍须检查数据源、缓存及截图中是否含私人路径。

若需要单独的本地验证工程，可将 `--output-dir` 指向不发布的目录，并用 `--data-folder <该目录/data的绝对路径>` 设置参数。正式公开工程不传此参数。

The repository contains an editable PBIP/PBIR project. Set the `DataFolder` Power Query parameter to your local `dashboard/data` folder and refresh in Power BI Desktop. Save the refreshed report as PBIX for an interactive demonstration; generate screenshots and a two-page PDF from Desktop.

## 指标与筛选

窗口为 **2017-02-01—2018-07-31**，按购买日期归属。金额使用源数据单位，币种未获得原作者直接说明，因此不标作 BRL。已交付商品金额不含运费，快照状态为 delivered；取消状态占比不是退款率。

日期与客户州维表同时单向筛选订单和明细事实表。品类仅关联明细，品类图所有向外视觉交互均关闭，不影响订单 KPI 和履约指标。品类组固定为整个窗口金额 Top10 与“其他”，日期/州切片后仍在这组定义内加总，合计等于已交付商品金额。

物流仅使用清洗流程的 `delivery_eligible`、`is_late` 和 `delivery_days`。同预计自然日送达算准时；缺日期不进入配送分母，也不从经营金额中删除。低评分为 1 或 2 分；组间比较使用日期与评分交集。各比例和 AOV 均动态汇总分子/分母后相除，零分母为空值。州散点仅显示至少 100 个已交付订单的州；任一准时/延迟分层组少于 30 时仅描述样本，不作重点判断。

## 对账

在 Desktop 的 DAX 查询视图分别运行：

- `reconciliation/all.dax`：整个窗口。
- `reconciliation/month_2017_02.dax`：2017 年 2 月。
- `reconciliation/state_SP.dax`：SP 州。

同一查询也复制在 `Olist.SemanticModel/DAXQueries/`。逐字段比对 `reconciliation/expected.json` 和 SQL 实际结果：订单数、分子、分母必须相同；商品金额误差不超过 0.01 源单位。`expected.json` 是从匿名 CSV 独立计算的预期值，**不是实际 DAX 执行证据**。Desktop 打开、刷新、DAX 执行、PBIX 保存及视觉检查另行记录。

## 导出接口与隐私

| 表 | 粒度 | 导出字段 |
|---|---|---|
| fact_orders | 每订单一行；以 COUNTROWS 聚合 | customer_state, order_status, purchase_date, merchandise_value, delivery_days, delivery_eligible, is_late, review_score, review_eligible, review_before_delivery, delay_group |
| fact_order_items | 每订单明细一行；仅金额聚合 | category, customer_state, order_status, purchase_date, price |
| dim_date | 完整日序列 | date, month_start, year, quarter, month, month_label |
| dim_customer_state | 每客户州一行 | customer_state |
| dim_category | 每品类一行 | category, category_group |

专用 CSV 删除客户标识、订单/商品标识、评价原文和无关字段；不导入复购附表。原始源数据保留在本地受忽略目录。匿名派生数据遵循原数据 [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) 条件，来源：[Olist 官方数据集](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)。

## 格式依据

采用微软公开支持的 [PBIP 项目结构](https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-overview)、[PBIR 报表结构](https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-report)和 [model.bim / TMSL 语义模型结构](https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-dataset)。模型无需同时保存 TMDL；[TMDL](https://learn.microsoft.com/en-us/analysis-services/tmdl/tmdl-overview) 是另一种受支持的语义模型表示。

`schemas/` 保存 [microsoft/json-schemas](https://github.com/microsoft/json-schemas) 的所用官方规范与其 MIT 许可，以便离线验证。验证入口：`python -m pytest tests/test_dashboard.py`。schema 验证确认 JSON 格式，不能替代 Desktop 的数据刷新、DAX 对账和视觉验收。
