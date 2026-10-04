# -*- coding: utf-8 -*-
"""Build public aggregate reports from a successful immutable pipeline run."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

SAMPLES = ("ALL_JOINT", "EXCLUDE_EARLY_ANSWERS")
PUBLIC_QUERIES = (1, 2, 3, 4, 5, 6, 7, 8, 10)
SOURCE_URL = "https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce"
LICENSE_URL = "https://creativecommons.org/licenses/by-nc-sa/4.0/"
PRIVATE_COLUMNS = {"order_id", "customer_id", "customer_unique_id", "first_order_id",
    "next_order_id", "review_id", "review_comment_title", "review_comment_message",
    "seller_id", "product_id"}


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def aggregate_sensitivity(rows, min_group_orders=30):
    """Sum count numerators and denominators; never average stratum percentages."""
    summaries = {}
    for sample in SAMPLES:
        selected = [row for row in rows if row["sample"] == sample]
        summary = {"joint_eligible_orders": 0, "answer_timestamp_orders": 0,
            "early_answer_orders": 0, "populated_strata": 0, "qualified_strata": 0,
            "qualified_joint_orders": 0, "positive_gap_strata": 0,
            "negative_gap_strata": 0, "equal_gap_strata": 0,
            "on_time": {"orders": 0, "low_score_orders": 0},
            "late": {"orders": 0, "low_score_orders": 0}}
        for row in selected:
            on_time, late = int(row["on_time_orders"]), int(row["late_orders"])
            joint = int(row["joint_eligible_orders"])
            summary["joint_eligible_orders"] += joint
            summary["answer_timestamp_orders"] += int(row["answer_timestamp_orders"])
            summary["early_answer_orders"] += int(row["early_answer_orders"])
            summary["populated_strata"] += joint > 0
            for group in ("on_time", "late"):
                summary[group]["orders"] += int(row[group + "_orders"])
                summary[group]["low_score_orders"] += int(row[group + "_low_score_orders"])
            if on_time >= min_group_orders and late >= min_group_orders:
                summary["qualified_strata"] += 1
                summary["qualified_joint_orders"] += joint
                gap = int(row["late_low_score_orders"]) / late - int(row["on_time_low_score_orders"]) / on_time
                if gap > 1e-12:
                    summary["positive_gap_strata"] += 1
                elif gap < -1e-12:
                    summary["negative_gap_strata"] += 1
                else:
                    summary["equal_gap_strata"] += 1
        for group in ("on_time", "late"):
            summary[group]["low_score_share"] = ratio(summary[group]["low_score_orders"], summary[group]["orders"])
        summary["low_score_share_gap"] = (summary["late"]["low_score_share"] - summary["on_time"]["low_score_share"]
            if summary["late"]["low_score_share"] is not None and summary["on_time"]["low_score_share"] is not None else None)
        summary["answer_timestamp_coverage"] = ratio(summary["answer_timestamp_orders"], summary["joint_eligible_orders"])
        summary["qualified_joint_coverage"] = ratio(summary["qualified_joint_orders"], summary["joint_eligible_orders"])
        summaries[sample] = summary
    return summaries


def load_successful_run(run_dir):
    if (run_dir / "failed.json").exists():
        raise ValueError("拒绝生成报告：运行目录含 failed.json")
    results = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    quality = json.loads((run_dir / "quality.json").read_text(encoding="utf-8"))
    for evidence in (results, quality, results.get("quality", {})):
        if evidence.get("status") != "passed" or evidence.get("blocking_failures", 0) != 0:
            raise ValueError("拒绝生成报告：运行或必要质量检查未通过")
    for evidence in (quality, results["quality"]):
        if any(check.get("severity") == "error" and not check.get("passed") for check in evidence.get("checks", [])):
            raise ValueError("拒绝生成报告：存在失败的必要检查")
    analyses = {}
    for number in PUBLIC_QUERIES:
        found = [(key, value) for key, value in results["analyses"].items() if key.startswith(f"q{number:02}_")]
        if len(found) != 1:
            raise ValueError(f"Q{number:02} 必须且只能有一个聚合结果")
        key, value = found[0]
        columns = value["columns"]
        if PRIVATE_COLUMNS.intersection(columns) or any(PRIVATE_COLUMNS.intersection(row) for row in value["records"]):
            raise ValueError(f"Q{number:02} 含客户/订单标识或评价原文，不可公开")
        if value["rows"] != len(value["records"]):
            raise ValueError(f"Q{number:02} 行数元数据不一致")
        analyses[key] = {"rows": value["rows"], "columns": columns, "records": value["records"]}
    results = dict(results, analyses=analyses)
    return results, quality


def query_records(results, number):
    return next(value["records"] for key, value in results["analyses"].items() if key.startswith(f"q{number:02}_"))


def decimal(value):
    return Decimal(str(value))


def pct(value):
    return "无适用分母" if value is None else f"{value:.2%}"


def money(value):
    return f"{decimal(value):,.2f}"


def count(value):
    return f"{int(value):,}"


def summarize(results):
    monthly = query_records(results, 1)
    delivered = sum(int(row["delivered_orders"]) for row in monthly)
    merchandise = sum((decimal(row["merchandise_value"]) for row in monthly), Decimal("0"))
    all_orders = sum(int(row["all_orders"]) for row in monthly)
    canceled = sum(int(row["canceled_orders"]) for row in monthly)
    changes = [row for row in query_records(results, 2) if row["merchandise_change"] is not None
               and row["order_count_contribution"] is not None and row["average_order_value_contribution"] is not None]
    largest_change = max(changes, key=lambda row: abs(decimal(row["merchandise_change"])), default=None)
    states = query_records(results, 4)
    priority = sorted((row for row in states if row["investigation_rank"] is not None), key=lambda row: row["investigation_rank"])
    coverage_rows = query_records(results, 6)
    delivery_n = sum(int(row["delivery_eligible_orders"]) for row in coverage_rows)
    review_n = sum(int(row["review_eligible_orders"]) for row in coverage_rows)
    joint_n = sum(int(row["joint_eligible_orders"]) for row in coverage_rows)
    late_n = sum(int(row["late_orders"]) for row in coverage_rows)
    duration = next(row for row in query_records(results, 5) if row["scope"] == "WINDOW")
    sensitivity = aggregate_sensitivity(query_records(results, 8), results["config"]["min_group_orders"])
    cohorts = query_records(results, 10)
    partial_cohorts = [row for row in cohorts if int(row["total_customers"]) > 0
                       and (int(row["eligible_customers"]) < int(row["total_customers"])
                            or not row["fully_observed_calendar_cohort"])]
    return {"merchandise_value": merchandise, "delivered_orders": delivered,
        "all_orders": all_orders, "canceled_orders": canceled,
        "average_order_value": merchandise / delivered if delivered else None,
        "canceled_order_share": ratio(canceled, all_orders), "largest_month_change": largest_change,
        "investigation_states": priority[:3], "delivery_eligible_orders": delivery_n,
        "late_orders": late_n, "late_share": ratio(late_n, delivery_n),
        "delivery_coverage": ratio(delivery_n, delivered), "review_coverage": ratio(review_n, delivered),
        "joint_eligible_orders": joint_n, "joint_coverage": ratio(joint_n, delivered),
        "duration": duration, "sensitivity": sensitivity, "partial_cohorts": partial_cohorts}


def analysis_markdown(results, overview):
    cfg = results["config"]
    change = overview["largest_month_change"]
    if change:
        change_text = (f"绝对金额变化最大的相邻月是 {str(change['purchase_month'])[:7]}，"
            f"金额差 {money(change['merchandise_change'])}（{pct(change['merchandise_change_rate'])}）；"
            f"订单数贡献 {money(change['order_count_contribution'])}，客单价贡献 {money(change['average_order_value_contribution'])}。")
    else:
        change_text = "可定义客单价的相邻月份不足，未作量价分解。"
    state_text = "；".join(f"{r['customer_state']}：已交付 {count(r['delivered_orders'])} 单，"
        f"延迟 {count(r['late_orders'])}/{count(r['delivery_eligible_orders'])}（{pct(r['late_share'])}），"
        f"日期覆盖 {pct(r['delivery_coverage'])}" for r in overview["investigation_states"])
    state_text = state_text or "没有州达到订单规模与有效物流样本规则，未排名。"
    all_s = overview["sensitivity"]["ALL_JOINT"]
    filtered = overview["sensitivity"]["EXCLUDE_EARLY_ANSWERS"]
    def group_text(summary, group):
        row = summary[group]
        return f"{count(row['low_score_orders'])}/{count(row['orders'])}（{pct(row['low_score_share'])}）"
    def strata_text(summary):
        return (f"{summary['qualified_strata']}/{summary['populated_strata']} 个有样本分层合格，覆盖交集样本 {pct(summary['qualified_joint_coverage'])}；"
            f"延迟低评分比例较高/较低/相同的合格组分别 {summary['positive_gap_strata']}/{summary['negative_gap_strata']}/{summary['equal_gap_strata']}")
    partial_text = "；".join(f"{str(row['cohort_month'])[:7]} 为部分成熟：{count(row['eligible_customers'])}/{count(row['total_customers'])} 客户成熟"
        f"（覆盖 {pct(row['observation_coverage'])}），30 天复购 {count(row['repeat_customers_30d'])}/{count(row['eligible_customers'])}"
        for row in overview["partial_cohorts"])
    partial_text = partial_text or "展示月份中的观测客户均有完整 30 天观察期。"
    aov = money(overview["average_order_value"]) if overview["average_order_value"] is not None else "无适用订单"
    return f"""# Olist 经营与履约诊断：一页结论

购买窗口 **{cfg['analysis_start']}—{cfg['analysis_end']}**；购买事件观察截止 **{cfg['observation_end']}**。商品金额为最终 delivered 订单的明细 price，不含运费；金额以**原始数据单位（币种未核验）**展示。

## 1. 经营变化可拆成订单数与客单价的算术贡献

**观察：**窗口已交付商品成交额 {money(overview['merchandise_value'])}，{count(overview['delivered_orders'])} 单，商品客单价 {aov}；取消状态占比 {count(overview['canceled_orders'])}/{count(overview['all_orders'])}={pct(overview['canceled_order_share'])}。{change_text}

**证据：**Q01 月度明细、Q02 顺序分解；Q03 的 Top 10 加“其他”金额与订单事实及每月金额一致，见质量报告。**建议：**针对金额变化最大的月份，进一步核对活动、商品组合和供给记录。**不能推出：**这是快照已交付商品金额，非收入、利润或退款率；先订单数后客单价的分解仅解释算术构成，不证明因果。

## 2. 州调查优先级同时保留规模、延迟分母与日期覆盖

**观察：**有效物流 {count(overview['delivery_eligible_orders'])}/{count(overview['delivered_orders'])}（{pct(overview['delivery_coverage'])}），延迟 {count(overview['late_orders'])}/{count(overview['delivery_eligible_orders'])}（{pct(overview['late_share'])}）。按延迟比例排序且已交付订单≥{cfg['min_state_orders']} 的前三州：{state_text}。

**证据：**Q04 州明细、Q06 月份×州覆盖；Q05 送达时长中位数 {overview['duration']['median_delivery_days']:.2f} 天、P90 {overview['duration']['p90_delivery_days']:.2f} 天，时长样本 {count(overview['duration']['duration_eligible_orders'])} 单。**建议：**优先调查这些州的承运、承诺日期与旺季记录，再检验问题是否跨月持续。**不能推出：**展示阈值不代表显著性；缺日期不算准时，州排名不是综合损失评分，也不能折算成收入损失。

## 3. 配送与低评分有关联，评价时序筛选改变样本组成

**观察：**Q07 全部交集的准时低评分为 {group_text(all_s, 'on_time')}，延迟为 {group_text(all_s, 'late')}；交集覆盖已交付订单 {pct(overview['joint_coverage'])}，评价覆盖 {pct(overview['review_coverage'])}。其中 {count(all_s['early_answer_orders'])} 单回答早于实际送达。Q08 剔除这些记录后，准时为 {group_text(filtered, 'on_time')}，延迟为 {group_text(filtered, 'late')}，交集样本从 {count(all_s['joint_eligible_orders'])} 变为 {count(filtered['joint_eligible_orders'])}；回答时间覆盖从 {pct(all_s['answer_timestamp_coverage'])} 变为 {pct(filtered['answer_timestamp_coverage'])}。

**证据：**同月份×州、准时与延迟各≥{cfg['min_group_orders']} 单的 Q08 分层中，全样本：{strata_text(all_s)}；剔除后：{strata_text(filtered)}。**建议：**补充评价发起规则、承运事件和商品组合，复核时间字段并在相同客户/商品条件下继续调查。**不能推出：**筛选改变了样本选择和两组分母，不能把差异变化当作因果校正；缺回答时间者保留并单列覆盖，不能推断其评价时点。整体或分层关系均不能证明延迟导致低评分。

**复购附表（Q09/Q10）：**首次观测使用完整源历史并按 customer_unique_id 去重；恰好第30天计入、等时订单不算后续。{partial_text}。部分成熟月份不参与完整月比较，也不作 cohort 排名；观测复购不能直接解释为经营失败。

来源：[Olist 官方数据卡]({SOURCE_URL})，数据与这些衍生分析遵循 [CC BY-NC-SA 4.0]({LICENSE_URL})；本项目进行了类型清洗、订单聚合、窗口筛选和统计汇总。图表见 `images/commerce-trend.png`、`images/review-sensitivity.png`；全部分子分母见 `analysis-results.json`。
"""


def quality_markdown(results, quality, manifest):
    checks = quality["checks"]
    errors = [check for check in checks if check["severity"] == "error"]
    warnings = [check for check in checks if check["severity"] == "warning" and not check["passed"]]
    rows = ["# 数据质量与复现证据", "", f"必要检查 {len(errors)}/{len(errors)} 通过，阻断失败 {quality['blocking_failures']}；非零警告 {len(warnings)} 项。",
        "", "本报告只接受成功运行。检查包含业务键/关联粒度、金额有效性、缺明细、事实金额、月度与 Top 10 加其他对账、量价分解残差。下表质量计数覆盖**全源模型**；一页结论则使用配置购买窗口，二者分母不同。",
        "", "| 非零警告 | 值 | 解释 |", "|---|---:|---|"]
    meanings = {
        "products.missing_category":"金额保留，缺原品类归 UNKNOWN。",
        "products.untranslated_category":"保留原品类名称，不误归缺失品类。",
        "delivery.missing_or_invalid":"订单保留经营金额，退出对应物流分母。",
        "delivery.invalid_sequence":"实际送达早于购买，退出物流口径。",
        "delivered.missing_payment":"支付不替代商品成交额，不自动删除订单。",
        "payment.reconciliation_difference":"支付与商品加运费有差异，保留原值。",
        "payment.reconciliation_difference_gt_cent":"绝对支付核对差异超过 0.01 原始单位。",
        "reviews.multiple_orders":"按回答时间、创建时间、review_id 选择一条；评价不参与金额聚合。",
        "reviews.missing_or_invalid":"退出评分分母；不算低评分或高评分。",
        "reviews.before_delivery":"有效交集中的回答早于送达，进行 Q08 时序敏感性对照。",
    }
    for check in warnings:
        rows.append(f"| {check['check']} | {check['value']} | {meanings.get(check['check'], check.get('note') or '保留异常并披露适用分母。')} |")
    rows += ["", "所有必需检查及对账的原始统计：", "", "| 检查 | 值 | 级别 | 结果 |", "|---|---:|---|---|"]
    for check in checks:
        rows.append(f"| {check['check']} | {check['value']} | {check['severity']} | {'通过' if check['passed'] else '警告' if check['severity']=='warning' else '失败'} |")
    rows += ["", "来源文件与快照证据（只展示文件名与摘要，不含个人本地路径或记录标识）：", "", "| CSV | 行数 | SHA-256 |", "|---|---:|---|"]
    for item in manifest.get("files", []):
        rows.append(f"| {item['filename']} | {count(item['rows'])} | `{item['sha256']}` |")
    runtime = results.get("runtime", {})
    rows += ["", f"Python {runtime.get('python','未记录')}；DuckDB {runtime.get('duckdb','未记录')}；本次流水线实测 {runtime.get('elapsed_seconds','未记录')} 秒。耗时包含导入、质量检查与导出，受电脑环境影响。",
        "", f"购买窗口 {results['config']['analysis_start']}—{results['config']['analysis_end']}；观察截止 {results['config']['observation_end']}；冻结窗口依据逐日源覆盖审核，不能被更晚物流/评价或稀疏购买尾段延长。",
        "", f"快照指纹 `{results.get('source_fingerprint','未记录')}`。", "",
        f"来源：[Olist 数据卡]({SOURCE_URL})；许可：[CC BY-NC-SA 4.0]({LICENSE_URL})。金额为原始数据单位（币种未核验）；本项目进行了清洗、聚合和统计分析。", ""]
    return "\n".join(rows)


def configure_plotting():
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import font_manager
    import matplotlib.pyplot as plt
    for filename in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf"):
        path = Path(filename)
        if path.exists():
            font_manager.fontManager.addfont(str(path))
            plt.rcParams["font.family"] = font_manager.FontProperties(fname=str(path)).get_name()
            break
    plt.rcParams.update({"font.size":11, "axes.titlesize":13, "axes.labelsize":11,
        "axes.spines.top":False, "axes.spines.right":False, "axes.unicode_minus":False,
        "savefig.facecolor":"white", "figure.facecolor":"white"})
    return plt


def create_figures(results, overview, images_dir):
    plt = configure_plotting()
    from matplotlib.ticker import PercentFormatter, StrMethodFormatter
    monthly = query_records(results, 1)
    cfg = results["config"]
    positions = list(range(len(monthly)))
    fig, axes = plt.subplots(3,1,figsize=(11.7,7.3),sharex=True,
                             gridspec_kw={"height_ratios":[2.1,1,1]},layout=None)
    axes[0].plot(positions, [float(row["merchandise_value"])/1000 for row in monthly], color="#164B72", marker="o", linewidth=2)
    axes[1].plot(positions, [int(row["delivered_orders"]) for row in monthly], color="#178176", marker="o", linewidth=1.7)
    axes[2].plot(positions, [row["average_order_value"] for row in monthly], color="#A66D1B", marker="o", linewidth=1.7)
    labels = ["商品成交额\n（千，原始单位）", "已交付订单\n（笔）", "商品客单价\n（原始单位）"]
    for panel, axis, label in zip("ABC",axes,labels):
        axis.set_ylabel(label)
        axis.text(.006,.965,panel,transform=axis.transAxes,ha="left",va="top",fontweight="bold")
        axis.grid(axis="y",alpha=.23)
        axis.yaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))
    axes[0].set_title(f"Olist 月度经营趋势 | {cfg['analysis_start']}—{cfg['analysis_end']}",loc="left",pad=13)
    ticks = positions[::2]
    if positions and positions[-1] not in ticks:
        ticks.append(positions[-1])
    axes[2].set_xticks(ticks,[str(monthly[i]["purchase_month"])[:7] for i in ticks],rotation=35,ha="right")
    axes[2].set_xlabel("订单购买月份")
    fig.subplots_adjust(left=.14,right=.97,top=.91,bottom=.25,hspace=.31)
    fig.text(.14,.08,f"已交付 {count(overview['delivered_orders'])} 单；最终 delivered 快照；按购买月；商品金额不含运费。",fontsize=10)
    fig.text(.14,.045,"来源：Olist/Kaggle，CC BY-NC-SA 4.0；原始数据单位（币种未核验）。",fontsize=9,color="#555555")
    fig.savefig(images_dir/"commerce-trend.png",dpi=240)
    plt.close(fig)

    fig, axis = plt.subplots(figsize=(11.7,7.0))
    colors = ("#178176", "#BD5B4C")
    sample_labels = []
    for index, sample in enumerate(SAMPLES):
        summary = overview["sensitivity"][sample]
        sample_labels.append(("全部合格交集" if sample=="ALL_JOINT" else "剔除提前回答")
            + f"\n交集 n={count(summary['joint_eligible_orders'])}，回答时间覆盖 {pct(summary['answer_timestamp_coverage'])}")
        for group_index, group in enumerate(("on_time","late")):
            row = summary[group]
            value = row["low_score_share"]
            x = index + (-.19 if group_index==0 else .19)
            axis.bar(x,0 if value is None else value,width=.34,color=colors[group_index],
                     label=("准时" if group=="on_time" else "延迟") if index==0 else None)
            axis.text(x,(value or 0)+.017,("无适用样本" if value is None else f"{value:.1%}\n{count(row['low_score_orders'])}/{count(row['orders'])}"),
                      ha="center",va="bottom",fontsize=11)
    maximum = max((overview["sensitivity"][sample][group]["low_score_share"] or 0 for sample in SAMPLES for group in ("on_time","late")),default=.1)
    axis.set_ylim(0,max(.20,maximum+.16))
    axis.set_xticks([0,1],sample_labels)
    axis.yaxis.set_major_formatter(PercentFormatter(1.0))
    axis.set_ylabel("低评分比例：1—2分 / 有效配送与评分交集")
    axis.set_title("配送与低评分关联：评价时序敏感性对照",loc="left",pad=17)
    axis.grid(axis="y",alpha=.23)
    axis.set_axisbelow(True)
    axis.legend(frameon=False,loc="upper right")
    fig.subplots_adjust(left=.11,right=.96,top=.88,bottom=.27)
    all_s, filtered = (overview["sensitivity"][sample] for sample in SAMPLES)
    fig.text(.11,.13,f"月份×州中准时/延迟各≥{cfg['min_group_orders']}单：全部合格组 {all_s['qualified_strata']}，剔除后 {filtered['qualified_strata']}；缺回答时间保留并单列覆盖。",fontsize=10)
    fig.text(.11,.095,f"剔除提前回答 {count(all_s['early_answer_orders'])} 单改变样本选择及组内分母；观察性对照不证明因果。",fontsize=10)
    fig.text(.11,.052,f"购买窗口：{cfg['analysis_start']}—{cfg['analysis_end']}。来源：Olist/Kaggle，CC BY-NC-SA 4.0。",fontsize=9,color="#555555")
    fig.savefig(images_dir/"review-sensitivity.png",dpi=240)
    plt.close(fig)


def build_reports(run_dir, output_dir):
    # All validation, calculations, and text rendering precede any output mutation.
    results, quality = load_successful_run(Path(run_dir))
    overview = summarize(results)
    summary_text = analysis_markdown(results, overview)
    manifest_path = Path(run_dir)/"source_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    quality_text = quality_markdown(results,quality,manifest)
    public = {"status":"passed", "config":results["config"],
        "source":{"url":SOURCE_URL,"license":"CC BY-NC-SA 4.0","license_url":LICENSE_URL,
                  "currency":"原始数据单位（币种未核验）","source_fingerprint":results.get("source_fingerprint")},
        "runtime":results.get("runtime",{}), "overview":overview, "analyses":results["analyses"]}
    public_text = json.dumps(public,ensure_ascii=False,indent=2,default=lambda value:str(value),allow_nan=False)+"\n"
    output_dir = Path(output_dir)
    output_dir.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".reports-",dir=output_dir.parent) as temporary:
        candidate = Path(temporary)
        (candidate/"images").mkdir()
        (candidate/"analysis-summary.md").write_text(summary_text,encoding="utf-8")
        (candidate/"analysis-results.json").write_text(public_text,encoding="utf-8")
        (candidate/"quality-report.md").write_text(quality_text,encoding="utf-8")
        cohort = next(value for key,value in results["analyses"].items() if key.startswith("q10_"))
        with (candidate/"cohort-30d.csv").open("w",encoding="utf-8",newline="") as stream:
            writer=csv.DictWriter(stream,fieldnames=cohort["columns"],lineterminator="\n")
            writer.writeheader()
            writer.writerows(cohort["records"])
        create_figures(results,overview,candidate/"images")
        for path in sorted(candidate.rglob("*")):
            if path.is_file():
                destination = output_dir/path.relative_to(candidate)
                destination.parent.mkdir(parents=True,exist_ok=True)
                path.replace(destination)
    return {"output_dir":str(output_dir),"artifacts":6,"delivered_orders":overview["delivered_orders"],
            "merchandise_value":str(overview["merchandise_value"])}


def main(argv=None):
    parser=argparse.ArgumentParser(description="从成功运行生成 Olist 聚合结论与真实统计图")
    parser.add_argument("--run-dir",type=Path,required=True)
    parser.add_argument("--output-dir",type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        summary=build_reports(args.run_dir,args.output_dir)
    except (OSError,ValueError,KeyError,TypeError) as error:
        print("报告生成失败："+str(error),file=sys.stderr)
        return 1
    print(json.dumps(summary,ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
