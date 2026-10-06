"""Build an editable, anonymous Power BI PBIP/PBIR project from approved CSVs.

The input retains order grain; the public export drops identifiers and raw reviews.
Automated tests validate Microsoft JSON schemas. Desktop refresh, DAX execution,
PBIX saving, and PDF export were not performed and are excluded from this delivery.
"""
import argparse
import csv
from datetime import date, timedelta
from decimal import Decimal
import hashlib
import json
from pathlib import Path


START = "2017-02-01"
END = "2018-07-31"
OBSERVATION_END = END + " 23:59:59"
SCHEMA = "https://developer.microsoft.com/json-schemas/"
TABLES = {
    "fact_orders": {
        "customer_state": "string", "order_status": "string", "purchase_date": "dateTime",
        "merchandise_value": "decimal", "delivery_days": "double", "delivery_eligible": "boolean",
        "is_late": "boolean", "review_score": "int64", "review_eligible": "boolean",
        "review_before_delivery": "boolean", "delay_group": "string",
    },
    "fact_order_items": {"category": "string", "customer_state": "string", "order_status": "string", "purchase_date": "dateTime", "price": "decimal"},
    "dim_date": {"date": "dateTime", "month_start": "dateTime", "year": "int64", "quarter": "int64", "month": "int64", "month_label": "string"},
    "dim_customer_state": {"customer_state": "string"},
    "dim_category": {"category": "string", "category_group": "string"},
}
LABELS = {
    "GMV": "已交付商品金额", "Delivered_Orders": "已交付订单数", "AOV": "商品客单价", "Cancel_Rate": "取消状态占比",
    "All_Orders": "窗口全部订单数", "Canceled_Orders": "取消订单数", "Item_GMV": "商品金额构成",
    "Delivery_Orders": "有效配送日期订单", "Late_Orders": "延迟订单数", "Late_Rate": "延迟送达比例",
    "P50_Days": "送达时长中位数（天）", "P90_Days": "送达时长P90（天）", "Review_Orders": "有效评分订单",
    "Low_Score_Orders": "低评分订单数", "Low_Score_Rate": "低评分比例", "Joint_Orders": "日期与评分交集订单",
    "Delivery_Coverage": "配送日期覆盖", "Review_Coverage": "评分覆盖", "Joint_Coverage": "联合覆盖",
    "Group_Low_Rate": "交集样本低评分比例", "Group_Orders": "交集样本订单数", "State_Investigation_Orders": "已交付订单（≥100）",
    "Duration_Orders": "有效送达时长订单", "Duration_Coverage": "送达时长覆盖",
    "State_Investigation_Late_Rate": "延迟比例（≥100订单）", "State_Investigation_Late_Orders": "延迟订单数（≥100订单）",
    "customer_state": "客户州", "month_label": "购买月份", "date": "购买日期", "category_group": "全窗口Top10品类及其他", "delay_group": "准时／延迟",
}


def write_json(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def is_true(value):
    return str(value).lower() in ("true", "1")


def validate_successful_run(run_dir):
    """Fail closed before writing output or interpreting CSVs from a run."""
    run_dir = Path(run_dir)
    if (run_dir / "failed.json").exists():
        raise ValueError("Run contains failed.json; dashboard generation is refused")
    results = json.loads((run_dir / "results.json").read_text(encoding="utf-8-sig"))
    if not isinstance(results, dict) or results.get("status") != "passed":
        raise ValueError("results.json must report a passed pipeline run")
    quality = results.get("quality")
    if not isinstance(quality, dict) or quality.get("status") != "passed":
        raise ValueError("results.json must report passed quality checks")
    blocking = quality.get("blocking_failures")
    if type(blocking) is not int or blocking != 0:
        raise ValueError("results.json must report zero blocking quality failures")
    config = results.get("config")
    expected = {"analysis_start": START, "analysis_end": END, "observation_end": OBSERVATION_END}
    if not isinstance(config, dict):
        raise ValueError("results.json must contain the approved run config")
    for name, value in expected.items():
        if config.get(name) != value:
            raise ValueError("First-release dashboard requires config.%s = %s" % (name, value))
    return results


def load_exports(run_dir):
    """Validate all dependencies before touching an existing report."""
    validate_successful_run(run_dir)
    source = {}
    for name, columns in TABLES.items():
        path = run_dir / "csv" / (name + ".csv")
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            required = set(columns) - {"delay_group", "month_label", "category_group"}
            missing = required - set(reader.fieldnames or [])
            if missing:
                raise ValueError("%s missing required columns: %s" % (name, ", ".join(sorted(missing))))
            source[name] = list(reader)
    for name in ("fact_orders", "fact_order_items"):
        source[name] = [row for row in source[name] if START <= row["purchase_date"][:10] <= END]
    orders = source["fact_orders"]
    ids = [r.get("order_id") for r in orders]
    if all(ids) and len(ids) != len(set(ids)):
        raise ValueError("fact_orders is not one row per order")
    totals = {}
    for row in source["fact_order_items"]:
        if row["order_status"] == "delivered":
            totals[row["category"]] = totals.get(row["category"], Decimal(0)) + Decimal(row["price"])
    top = {key for key, _ in sorted(totals.items(), key=lambda pair: (-pair[1], pair[0]))[:10]}
    for row in orders:
        row["delay_group"] = ("延迟" if is_true(row["is_late"]) else "准时") if is_true(row["delivery_eligible"]) else "无有效日期"
    for row in source["dim_category"]:
        row["category_group"] = row["category"] if row["category"] in top else "其他"
    source["dim_date"] = []
    day, last = date.fromisoformat(START), date.fromisoformat(END)
    while day <= last:
        source["dim_date"].append({"date": day.isoformat(), "month_start": day.replace(day=1).isoformat(), "year": day.year, "quarter": (day.month - 1) // 3 + 1, "month": day.month, "month_label": day.strftime("%Y-%m")})
        day += timedelta(days=1)
    order_total = sum((Decimal(r["merchandise_value"]) for r in orders if r["order_status"] == "delivered"), Decimal(0))
    if order_total != sum(totals.values(), Decimal(0)):
        raise ValueError("Order and item delivered merchandise totals do not reconcile")
    return {name: [{field: row.get(field, "") for field in TABLES[name]} for row in rows] for name, rows in source.items()}


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def percentile(values, quantile):
    if not values:
        return None
    values = sorted(values)
    index = (len(values) - 1) * quantile
    lower = int(index)
    upper = min(lower + 1, len(values) - 1)
    return values[lower] + (values[upper] - values[lower]) * (index - lower)


def expected_metrics(rows):
    """Independent CSV-side reconciliation; never substitute for actual DAX."""
    delivered = [r for r in rows if r["order_status"] == "delivered"]
    delivery = [r for r in delivered if is_true(r["delivery_eligible"])]
    reviews = [r for r in delivered if is_true(r["review_eligible"])]
    joint = [r for r in delivery if is_true(r["review_eligible"])]
    canceled = sum(r["order_status"] == "canceled" for r in rows)
    late = sum(is_true(r["is_late"]) for r in delivery)
    low = sum(int(r["review_score"]) in (1, 2) for r in reviews)
    gmv = float(sum((Decimal(r["merchandise_value"]) for r in delivered), Decimal(0)))
    days = [float(r["delivery_days"]) for r in delivered if r["delivery_days"] not in (None, "")]
    return {"gmv": gmv, "delivered_orders": len(delivered), "aov": ratio(gmv, len(delivered)), "all_orders": len(rows), "canceled_orders": canceled, "cancel_rate": ratio(canceled, len(rows)), "delivery_orders": len(delivery), "late_orders": late, "late_rate": ratio(late, len(delivery)), "review_orders": len(reviews), "low_score_orders": low, "low_score_rate": ratio(low, len(reviews)), "joint_orders": len(joint), "delivery_coverage": ratio(len(delivery), len(delivered)), "duration_orders": len(days), "duration_coverage": ratio(len(days), len(delivered)), "review_coverage": ratio(len(reviews), len(delivered)), "joint_coverage": ratio(len(joint), len(delivered)), "p50_days": percentile(days, 0.5), "p90_days": percentile(days, 0.9)}


def measures():
    delivered = "fact_orders[order_status] = \"delivered\""
    delivery = delivered + ", fact_orders[delivery_eligible] = TRUE()"
    review = delivered + ", fact_orders[review_eligible] = TRUE()"
    joint = delivery + ", fact_orders[review_eligible] = TRUE()"
    raw = {
        "GMV": "CALCULATE(SUM(fact_orders[merchandise_value]), " + delivered + ")",
        "Delivered_Orders": "CALCULATE(COUNTROWS(fact_orders), " + delivered + ")",
        "AOV": "DIVIDE([GMV], [Delivered_Orders])",
        "All_Orders": "COUNTROWS(fact_orders)",
        "Canceled_Orders": "CALCULATE(COUNTROWS(fact_orders), fact_orders[order_status] = \"canceled\")",
        "Cancel_Rate": "DIVIDE([Canceled_Orders], [All_Orders])",
        "Delivery_Orders": "CALCULATE(COUNTROWS(fact_orders), " + delivery + ")",
        "Late_Orders": "CALCULATE(COUNTROWS(fact_orders), " + delivery + ", fact_orders[is_late] = TRUE())",
        "Late_Rate": "DIVIDE([Late_Orders], [Delivery_Orders])",
        "Review_Orders": "CALCULATE(COUNTROWS(fact_orders), " + review + ")",
        "Low_Score_Orders": "CALCULATE(COUNTROWS(fact_orders), " + review + ", fact_orders[review_score] IN {1, 2})",
        "Low_Score_Rate": "DIVIDE([Low_Score_Orders], [Review_Orders])",
        "Joint_Orders": "CALCULATE(COUNTROWS(fact_orders), " + joint + ")",
        "Delivery_Coverage": "DIVIDE([Delivery_Orders], [Delivered_Orders])",
        "Review_Coverage": "DIVIDE([Review_Orders], [Delivered_Orders])",
        "Joint_Coverage": "DIVIDE([Joint_Orders], [Delivered_Orders])",
        "Duration_Orders": "CALCULATE(COUNT(fact_orders[delivery_days]), " + delivered + ")",
        "Duration_Coverage": "DIVIDE([Duration_Orders], [Delivered_Orders])",
        "P50_Days": "CALCULATE(PERCENTILE.INC(fact_orders[delivery_days], 0.5), " + delivered + ", NOT ISBLANK(fact_orders[delivery_days]))",
        "P90_Days": "CALCULATE(PERCENTILE.INC(fact_orders[delivery_days], 0.9), " + delivered + ", NOT ISBLANK(fact_orders[delivery_days]))",
        "Group_Orders": "CALCULATE(COUNTROWS(fact_orders), " + joint + ")",
        "Group_Low_Orders": "CALCULATE(COUNTROWS(fact_orders), " + joint + ", fact_orders[review_score] IN {1, 2})",
        "Group_Low_Rate": "DIVIDE([Group_Low_Orders], [Group_Orders])",
        "State_Investigation_Orders": "IF([Delivered_Orders] >= 100, [Delivered_Orders])",
        "State_Investigation_Late_Rate": "IF([Delivered_Orders] >= 100, [Late_Rate])",
        "State_Investigation_Late_Orders": "IF([Delivered_Orders] >= 100, [Late_Orders])",
    }
    output = []
    for name, expression in raw.items():
        if name in ("GMV", "All_Orders", "Delivered_Orders", "Canceled_Orders", "Delivery_Orders", "Duration_Orders", "Late_Orders", "Review_Orders", "Low_Score_Orders", "Joint_Orders", "Group_Orders", "Group_Low_Orders"):
            expression = "COALESCE(" + expression + ", 0)"
        fmt = "0.0%" if "Rate" in name or "Coverage" in name else "#,0.00" if name in ("GMV", "AOV", "P50_Days", "P90_Days") else "#,0"
        output.append({"name": name, "expression": expression, "formatString": fmt, "displayFolder": "经营" if name in ("GMV", "Delivered_Orders", "AOV", "All_Orders", "Canceled_Orders", "Cancel_Rate") else "履约", "description": LABELS.get(name, name) + "；按日期与州筛选后重新聚合，空分母返回空值。"})
    return output


def m_partition(name, columns):
    types = {"string": "type text", "dateTime": "type date", "decimal": "Currency.Type", "double": "type number", "boolean": "type logical", "int64": "Int64.Type"}
    transformations = ", ".join('{"%s", %s}' % (field, types[dtype]) for field, dtype in columns.items())
    source = ["let", '    Source = Csv.Document(File.Contents(DataFolder & "/' + name + '.csv"), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),', "    Headers = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),", "    Nulls = Table.ReplaceValue(Headers, \"\", null, Replacer.ReplaceValue, Table.ColumnNames(Headers)),", "    Typed = Table.TransformColumnTypes(Nulls, {" + transformations + '}, "en-US")', "in", "    Typed"]
    return {"name": name, "mode": "import", "source": {"type": "m", "expression": source}}


def semantic_model(data_folder=None):
    tables = []
    for name, fields in TABLES.items():
        columns = []
        for field, dtype in fields.items():
            column = {"name": field, "dataType": dtype, "sourceColumn": field, "summarizeBy": "none"}
            if dtype == "dateTime":
                column.update({"formatString": "yyyy-MM-dd", "annotations": [{"name": "UnderlyingDateTimeDataType", "value": "Date"}]})
            if dtype == "decimal":
                column["formatString"] = "#,0.00"
            if field == "month_label":
                column["sortByColumn"] = "month_start"
            columns.append(column)
        table = {"name": name, "columns": columns, "partitions": [m_partition(name, fields)]}
        if name == "fact_orders":
            table["measures"] = measures()
        if name == "fact_order_items":
            table["measures"] = [{"name": "Item_GMV", "expression": 'CALCULATE(SUM(fact_order_items[price]), fact_order_items[order_status] = "delivered")', "formatString": "#,0.00", "description": "按购买日期／客户州／品类汇总的已交付商品金额，不影响订单级指标。"}]
        tables.append(table)
    relationships = []
    for fact in ("fact_orders", "fact_order_items"):
        for dim, fact_col, dim_col in [("dim_date", "purchase_date", "date"), ("dim_customer_state", "customer_state", "customer_state")]:
            relationships.append({"name": fact + "_" + dim, "fromTable": fact, "fromColumn": fact_col, "toTable": dim, "toColumn": dim_col, "fromCardinality": "many", "toCardinality": "one", "crossFilteringBehavior": "oneDirection"})
    relationships.append({"name": "items_category", "fromTable": "fact_order_items", "fromColumn": "category", "toTable": "dim_category", "toColumn": "category", "fromCardinality": "many", "toCardinality": "one", "crossFilteringBehavior": "oneDirection"})
    folder = str(data_folder).replace("\\", "/") if data_folder else "C:/PATH/TO/dashboard/data"
    parameter = json.dumps(folder, ensure_ascii=False) + ' meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]'
    return {"name": "Olist", "compatibilityLevel": 1567, "model": {"culture": "en-US", "sourceQueryCulture": "en-US", "defaultPowerBIDataSourceVersion": "powerBI_V3", "tables": tables, "relationships": relationships, "expressions": [{"name": "DataFolder", "kind": "m", "expression": parameter}], "annotations": [{"name": "PBI_QueryOrder", "value": json.dumps(["DataFolder"] + list(TABLES))}, {"name": "PBI_TimeIntelligenceEnabled", "value": "0"}]}}


def expr(value):
    literal = "true" if value is True else "false" if value is False else str(value) + "D" if isinstance(value, (int, float)) else "'" + str(value).replace("'", "''") + "'"
    return {"expr": {"Literal": {"Value": literal}}}


def field(table, column, measure=False):
    return {"Measure" if measure else "Column": {"Expression": {"SourceRef": {"Entity": table}}, "Property": column}}


def projection(table, column, measure=False):
    return {"field": field(table, column, measure), "queryRef": table + "." + column, "nativeQueryRef": column, "displayName": LABELS.get(column, column)}


def visual(name, kind, title, x, y, width, height, roles=None, sort=None):
    config = {"visualType": kind, "visualContainerObjects": {"title": [{"properties": {"show": expr(True), "text": expr(title), "fontSize": expr(14), "fontColor": expr("#19384E"), "fontFamily": expr("Segoe UI"), "bold": expr(True)}}], "background": [{"properties": {"show": expr(True), "color": {"solid": {"color": expr("#FFFFFF")}}, "transparency": expr(0)}}], "border": [{"properties": {"show": expr(True), "color": {"solid": {"color": expr("#CBD5E1")}}, "radius": expr(10)}}], "general": [{"properties": {"altText": expr(title)}}]}}
    if roles:
        config["query"] = {"queryState": {role: {"projections": values} for role, values in roles.items()}}
        if sort:
            config["query"]["sortDefinition"] = {"sort": [{"field": sort[0], "direction": sort[1]}], "isDefaultSort": False}
    if kind == "card":
        config["objects"] = {"labels": [{"properties": {"fontSize": expr(32), "color": {"solid": {"color": expr("#1E40AF")}}}}], "categoryLabels": [{"properties": {"show": expr(False)}}]}
    return {"$schema": SCHEMA + "fabric/item/report/definition/visualContainer/1.0.0/schema.json", "name": name, "position": {"x": x, "y": y, "width": width, "height": height, "z": 0, "tabOrder": 0}, "visual": config}


def text_visual(name, text, x, y, width, height, size=14, color="#475569"):
    v = visual(name, "textbox", "", x, y, width, height)
    v["visual"]["visualContainerObjects"] = {"title": [{"properties": {"show": expr(False)}}]}
    v["visual"]["objects"] = {"general": [{"properties": {"paragraphs": [{"textRuns": [{"value": text, "textStyle": {"fontFamily": "Segoe UI", "fontSize": "%spt" % size, "color": color}}]}]}}]}
    return v


def report_pages(source_snapshot="unmarked"):
    result = {}
    for page, heading in [("commerce", "Olist 经营概览"), ("delivery", "Olist 履约诊断")]:
        snapshot_label = source_snapshot if len(source_snapshot) <= 24 else source_snapshot[:24] + "…"
        v = [text_visual("heading", heading, 28, 18, 1224, 48, 30, "#19384E"), text_visual("subheading", "2017-02-01 — 2018-07-31 · 快照 " + snapshot_label + " · 金额为源单位（币种未核验）", 28, 74, 1224, 44, 13)]
        v.append(visual("date_filter", "slicer", "购买日期 · 两页同步", 28, 134, 704, 88, {"Values": [projection("dim_date", "date")]}))
        v[-1]["visual"]["objects"] = {"data": [{"properties": {"mode": expr("Between")}}]}
        v[-1]["visual"]["syncGroup"] = {"groupName": "PurchaseDate", "fieldChanges": True, "filterChanges": True}
        v.append(visual("state_filter", "slicer", "客户收货州 · 两页同步", 748, 134, 504, 88, {"Values": [projection("dim_customer_state", "customer_state")]}))
        v[-1]["visual"]["objects"] = {"data": [{"properties": {"mode": expr("Dropdown")}}]}
        v[-1]["visual"]["syncGroup"] = {"groupName": "CustomerState", "fieldChanges": True, "filterChanges": True}
        card_measures = ["GMV", "Delivered_Orders", "AOV", "Cancel_Rate"] if page == "commerce" else ["Late_Rate", "P50_Days", "P90_Days", "Low_Score_Rate"]
        for index, name in enumerate(card_measures):
            title = LABELS[name] + ("（源币单位）" if name in ("GMV", "AOV") else "")
            v.append(visual("kpi_" + name, "card", title, 28 + index * 310, 242, 294, 124, {"Values": [projection("fact_orders", name, True)]}))
        if page == "commerce":
            for name, x, width in [("GMV", 28, 604), ("Delivered_Orders", 648, 294), ("AOV", 958, 294)]:
                v.append(visual("monthly_" + name, "lineChart", "月度" + LABELS[name], x, 390, width, 240, {"Category": [projection("dim_date", "month_label")], "Y": [projection("fact_orders", name, True)]}, (field("dim_date", "month_label"), "Ascending")))
            v.append(visual("category_amount", "barChart", "Top10品类 + 其他 · 商品金额构成", 28, 654, 604, 248, {"Category": [projection("dim_category", "category_group")], "Y": [projection("fact_order_items", "Item_GMV", True)]}, (field("fact_order_items", "Item_GMV", True), "Descending")))
            v.append(visual("state_amount", "barChart", "客户州 · 已交付商品金额", 648, 654, 604, 248, {"Category": [projection("dim_customer_state", "customer_state")], "Y": [projection("fact_orders", "GMV", True)]}, (field("fact_orders", "GMV", True), "Descending")))
            footer = "商品金额不含运费；按最终delivered状态及购买日统计。取消状态占比不是退款率。品类点击仅查看金额构成。"
        else:
            for index, name in enumerate(["Delivery_Coverage", "Review_Coverage", "Joint_Coverage"]):
                v.append(visual("coverage_" + name, "card", LABELS[name], 28 + index * 414, 390, 396, 100, {"Values": [projection("fact_orders", name, True)]}))
            v.append(visual("state_scatter", "scatterChart", "州调查 · 订单规模 × 延迟比例（≥100订单）", 28, 514, 604, 388, {"Category": [projection("dim_customer_state", "customer_state")], "X": [projection("fact_orders", "State_Investigation_Orders", True)], "Y": [projection("fact_orders", "State_Investigation_Late_Rate", True)], "Size": [projection("fact_orders", "State_Investigation_Late_Orders", True)], "Tooltips": [projection("fact_orders", n, True) for n in ("Delivery_Orders", "Late_Orders", "Low_Score_Rate", "Joint_Coverage")]}))
            v.append(visual("on_time_late", "clusteredColumnChart", "准时／延迟 · 交集样本低评分", 648, 514, 294, 388, {"Category": [projection("fact_orders", "delay_group")], "Y": [projection("fact_orders", "Group_Low_Rate", True)], "Tooltips": [projection("fact_orders", "Group_Orders", True)]}))
            v.append(visual("monthly_late", "lineChart", "按购买月份的延迟比例", 958, 514, 294, 388, {"Category": [projection("dim_date", "month_label")], "Y": [projection("fact_orders", "Late_Rate", True)]}, (field("dim_date", "month_label"), "Ascending")))
            footer = "同预计日送达算准时；缺日期退出物流分母。低评分=1/2分。组间比较仅日期与评分交集；任组<30不作重点判断，关系不表示因果。"
        v.append(text_visual("footer", footer, 28, 924, 1224, 64, 13))
        for index, item in enumerate(v):
            item["position"]["tabOrder"] = index
        page_doc = {"$schema": SCHEMA + "fabric/item/report/definition/page/1.0.0/schema.json", "name": page, "displayName": "经营概览" if page == "commerce" else "履约诊断", "displayOption": "FitToWidth", "width": 1280, "height": 1008, "objects": {"background": [{"properties": {"color": {"solid": {"color": expr("#F4F7FA")}}, "transparency": expr(0)}}]}, "annotations": [{"name": "sourceSnapshot", "value": source_snapshot}]}
        if page == "commerce":
            page_doc["visualInteractions"] = [{"source": "category_amount", "target": item["name"], "type": "NoFilter"} for item in v if item["name"] != "category_amount"]
        result[page] = (page_doc, v)
    return result


def reconciliation_queries(out, rows):
    targets = {"all": rows, "month_2017_02": [r for r in rows if r["purchase_date"].startswith("2017-02")], "state_SP": [r for r in rows if r["customer_state"] == "SP"]}
    write_json(out / "reconciliation" / "expected.json", {key: expected_metrics(value) for key, value in targets.items()})
    metric_map = [("gmv", "GMV"), ("delivered_orders", "Delivered_Orders"), ("aov", "AOV"), ("all_orders", "All_Orders"), ("canceled_orders", "Canceled_Orders"), ("cancel_rate", "Cancel_Rate"), ("delivery_orders", "Delivery_Orders"), ("late_orders", "Late_Orders"), ("late_rate", "Late_Rate"), ("review_orders", "Review_Orders"), ("low_score_orders", "Low_Score_Orders"), ("low_score_rate", "Low_Score_Rate"), ("joint_orders", "Joint_Orders"), ("delivery_coverage", "Delivery_Coverage"), ("review_coverage", "Review_Coverage"), ("joint_coverage", "Joint_Coverage"), ("p50_days", "P50_Days"), ("p90_days", "P90_Days")]
    metric_map += [("duration_orders", "Duration_Orders"), ("duration_coverage", "Duration_Coverage")]
    values = ",\n    ".join('"%s", [%s]' % (label, name) for label, name in metric_map)
    base = "ROW(\n    " + values + "\n)"
    filters = {"all": "", "month_2017_02": ", FILTER(ALL(dim_date), dim_date[date] >= DATE(2017,2,1) && dim_date[date] <= DATE(2017,2,28))", "state_SP": ', TREATAS({"SP"}, dim_customer_state[customer_state])'}
    folder = out / "Olist.SemanticModel" / "DAXQueries"
    folder.mkdir(parents=True, exist_ok=True)
    for name, clause in filters.items():
        query = "EVALUATE\n" + ("CALCULATETABLE(" + base + clause + ")" if clause else base) + "\n"
        (folder / (name + ".dax")).write_text(query, encoding="utf-8")
        (out / "reconciliation" / (name + ".dax")).write_text(query, encoding="utf-8")
        extra = " AND purchase_date BETWEEN DATE '2017-02-01' AND DATE '2017-02-28'" if name == "month_2017_02" else " AND customer_state = 'SP'" if name == "state_SP" else ""
        sql = """-- One row per order. Execute against the approved warehouse or anonymous export.
-- %s; purchase-date window. Currency is unverified source units.
WITH selected AS (
  SELECT * FROM fact_orders
  WHERE purchase_date BETWEEN DATE '%s' AND DATE '%s'%s
), counts AS (
  SELECT
    COALESCE(SUM(merchandise_value) FILTER (WHERE order_status='delivered'),0) AS gmv,
    COUNT(*) FILTER (WHERE order_status='delivered') AS delivered_orders,
    COUNT(*) AS all_orders,
    COUNT(*) FILTER (WHERE order_status='canceled') AS canceled_orders,
    COUNT(*) FILTER (WHERE order_status='delivered' AND delivery_eligible) AS delivery_orders,
    COUNT(*) FILTER (WHERE order_status='delivered' AND delivery_eligible AND is_late) AS late_orders,
    COUNT(*) FILTER (WHERE order_status='delivered' AND review_eligible) AS review_orders,
    COUNT(*) FILTER (WHERE order_status='delivered' AND review_eligible AND review_score IN (1,2)) AS low_score_orders,
    COUNT(*) FILTER (WHERE order_status='delivered' AND delivery_eligible AND review_eligible) AS joint_orders,
    COUNT(delivery_days) FILTER (WHERE order_status='delivered') AS duration_orders,
    QUANTILE_CONT(delivery_days,0.5) FILTER (WHERE order_status='delivered') AS p50_days,
    QUANTILE_CONT(delivery_days,0.9) FILTER (WHERE order_status='delivered') AS p90_days
  FROM selected
)
SELECT *,
  gmv / NULLIF(delivered_orders,0) AS aov,
  canceled_orders::DOUBLE / NULLIF(all_orders,0) AS cancel_rate,
  late_orders::DOUBLE / NULLIF(delivery_orders,0) AS late_rate,
  low_score_orders::DOUBLE / NULLIF(review_orders,0) AS low_score_rate,
  delivery_orders::DOUBLE / NULLIF(delivered_orders,0) AS delivery_coverage,
  review_orders::DOUBLE / NULLIF(delivered_orders,0) AS review_coverage,
  joint_orders::DOUBLE / NULLIF(delivered_orders,0) AS joint_coverage,
  duration_orders::DOUBLE / NULLIF(delivered_orders,0) AS duration_coverage
FROM counts;
""" % (name, START, END, extra)
        (out / "reconciliation" / (name + ".sql")).write_text(sql, encoding="utf-8")


THEME_FILENAME = "OlistFocus-c0a61e42.json"


def report_theme():
    """Native Power BI theme; formatting only, with no data or model changes."""
    return {
        "name": THEME_FILENAME,
        "dataColors": ["#1E40AF", "#0F766E", "#B45309", "#7E22CE", "#475569", "#B91C1C"],
        "background": "#FFFFFF", "foreground": "#19384E", "tableAccent": "#1E40AF",
        "good": "#0F766E", "neutral": "#B45309", "bad": "#B91C1C",
        "textClasses": {
            "label": {"fontFace": "Segoe UI", "fontSize": 13, "color": "#475569"},
            "title": {"fontFace": "Segoe UI", "fontSize": 16, "color": "#19384E"},
            "header": {"fontFace": "Segoe UI", "fontSize": 14, "color": "#19384E"},
            "callout": {"fontFace": "Segoe UI", "fontSize": 32, "color": "#1E40AF"},
        },
    }


def report_configuration():
    return {
        "$schema": SCHEMA + "fabric/item/report/definition/report/1.0.0/schema.json",
        "layoutOptimization": "None",
        "themeCollection": {
            "baseTheme": {"name": "CY24SU06", "reportVersionAtImport": "5.55", "type": "SharedResources"},
            "customTheme": {"name": THEME_FILENAME, "reportVersionAtImport": "5.55", "type": "RegisteredResources"},
        },
        "resourcePackages": [{"name": "RegisteredResources", "type": "RegisteredResources",
                              "items": [{"name": THEME_FILENAME, "path": THEME_FILENAME, "type": "CustomTheme"}]}],
    }


def build_dashboard(run_dir, output_dir, data_folder=None):
    run_dir, output_dir = Path(run_dir), Path(output_dir)
    exports = load_exports(run_dir)
    manifest_path = run_dir / "source_manifest.json"
    source_files = []
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        source_files = sorted((entry["filename"], entry["sha256"]) for entry in manifest.get("files", []))
    source_snapshot = hashlib.sha256(json.dumps(source_files, separators=(",", ":")).encode("utf-8")).hexdigest()[:12] if source_files else "unmarked"
    output_dir.mkdir(parents=True, exist_ok=True)
    data_dir = output_dir / "data"
    data_dir.mkdir(exist_ok=True)
    for name, rows in exports.items():
        with (data_dir / (name + ".csv")).open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(TABLES[name]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
    write_json(output_dir / "Olist.pbip", {"$schema": SCHEMA + "fabric/pbip/pbipProperties/1.0.0/schema.json", "version": "1.0", "artifacts": [{"report": {"path": "Olist.Report"}}], "settings": {"enableAutoRecovery": True}})
    write_json(output_dir / "Olist.SemanticModel" / "definition.pbism", {"$schema": SCHEMA + "fabric/item/semanticModel/definitionProperties/1.0.0/schema.json", "version": "1.0", "settings": {"qnaEnabled": False}})
    write_json(output_dir / "Olist.SemanticModel" / "model.bim", semantic_model(data_folder))
    report_dir = output_dir / "Olist.Report"
    write_json(report_dir / "definition.pbir", {"$schema": SCHEMA + "fabric/item/report/definitionProperties/2.0.0/schema.json", "version": "4.0", "datasetReference": {"byPath": {"path": "../Olist.SemanticModel"}}})
    definition = report_dir / "definition"
    write_json(definition / "version.json", {"$schema": SCHEMA + "fabric/item/report/definition/versionMetadata/1.0.0/schema.json", "version": "2.0.0"})
    write_json(definition / "report.json", report_configuration())
    write_json(report_dir / "StaticResources" / "RegisteredResources" / THEME_FILENAME, report_theme())
    write_json(definition / "pages" / "pages.json", {"$schema": SCHEMA + "fabric/item/report/definition/pagesMetadata/1.0.0/schema.json", "pageOrder": ["commerce", "delivery"], "activePageName": "commerce"})
    for page, (document, visuals) in report_pages(source_snapshot).items():
        write_json(definition / "pages" / page / "page.json", document)
        for item in visuals:
            write_json(definition / "pages" / page / "visuals" / item["name"] / "visual.json", item)
    reconciliation_queries(output_dir, exports["fact_orders"])
    write_json(output_dir / "build-manifest.json", {"analysis_start": START, "analysis_end": END, "observation_end": OBSERVATION_END, "source_snapshot": source_snapshot, "source_files": [{"filename": filename, "sha256": digest} for filename, digest in source_files], "currency": "unverified_source_units", "privacy": "No customer, order, or product identifiers; no raw review text", "tables": {name: {"rows": len(rows), "columns": list(TABLES[name])} for name, rows in exports.items()}, "sources": ["https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce", "https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-report", "https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-dataset", "https://github.com/microsoft/json-schemas"], "desktop_validation": "not_performed_scope_excluded", "desktop_scope_exclusions": ["refresh", "dax_reconciliation", "pbix", "pdf"], "format_validation": "Microsoft JSON-schema validation is covered by tests/test_dashboard.py"})
    (output_dir / ".gitignore").write_text("**/.pbi/localSettings.json\n**/.pbi/cache.abf\n**/.pbi/unappliedChanges.json\n", encoding="utf-8")
    return output_dir / "Olist.pbip"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("dashboard"))
    parser.add_argument("--data-folder", type=Path, help="Explicit local refresh path; do not publish a project with a personal path")
    args = parser.parse_args()
    print(build_dashboard(args.run_dir, args.output_dir, args.data_folder))


if __name__ == "__main__":
    main()
