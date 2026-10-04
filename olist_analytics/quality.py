"""Aggregate quality evidence; no source row identifiers or review text."""
from decimal import Decimal

KEYS = {"orders":["order_id"],"items":["order_id","order_item_id"],
        "payments":["order_id","payment_sequential"],"customers":["customer_id"],
        "products":["product_id"],"reviews":["review_id","order_id"],
        "category_translation":["product_category_name"]}

def _rec(check, value, severity="error", note=""):
    return {"check":check,"value":value,"severity":severity,"passed":value==0,"note":note}

def check_staging(c):
    checks = []
    def add(name, sql, severity="error", note=""):
        checks.append(_rec(name, c.execute(sql).fetchone()[0], severity, note))
    for table, keys in KEYS.items():
        joined = ", ".join(keys)
        add(table+".key_conflicts","SELECT COUNT(*) FROM (SELECT "+joined+" FROM stg_"+
            table+" GROUP BY "+joined+" HAVING COUNT(*)>1)")
        add(table+".missing_key","SELECT COUNT(*) FROM stg_"+table+" WHERE "+
            " OR ".join(key+" IS NULL" for key in keys))
        add(table+".exact_duplicate_rows","SELECT (SELECT COUNT(*) FROM raw_"+table+
            ")-(SELECT COUNT(*) FROM (SELECT DISTINCT * FROM raw_"+table+"))",
            "warning","Only identical records are deduplicated.")
    for table, column in [("items","price"),("items","freight_value"),("payments","payment_value")]:
        add(table+"."+column+".invalid_amount","SELECT COUNT(*) FROM stg_"+table+
            " WHERE "+column+" IS NULL OR "+column+"<0 OR NOT regexp_full_match(TRIM("+
            column+"_raw), '[+]?[0-9]+([.][0-9]{1,2})?')",
            note="Nonnegative amounts with at most two decimal places.")
    for table, column in [("items","order_item_id"),("payments","payment_sequential")]:
        add(table+"."+column+".invalid_key","SELECT COUNT(*) FROM stg_"+table+
            " WHERE "+column+" IS NULL OR "+column+"<=0 OR NOT regexp_full_match(TRIM("+
            column+"_raw), '[0-9]+')")
    add("orders.invalid_purchase_timestamp",
        "SELECT COUNT(*) FROM stg_orders WHERE order_purchase_timestamp IS NULL")
    add("customers.missing_unique_identifier",
        "SELECT COUNT(*) FROM stg_customers WHERE customer_unique_id IS NULL")
    add("orders.invalid_status","SELECT COUNT(*) FROM stg_orders WHERE order_status IS NULL "
        "OR order_status NOT IN ('created','approved','invoiced','processing','shipped',"
        "'delivered','unavailable','canceled')")
    add("reviews.invalid_score","SELECT COUNT(*) FROM stg_reviews WHERE review_score IS NULL "
        "OR review_score NOT BETWEEN 1 AND 5","warning","Excluded from rating denominator.")
    add("reviews.ambiguous_selection","SELECT COUNT(*) FROM (SELECT order_id, "
        "review_answer_timestamp,review_creation_date,review_id FROM stg_reviews "
        "GROUP BY ALL HAVING COUNT(DISTINCT review_score)>1)")
    for table, parent, key in [("orders","customers","customer_id"),("items","orders","order_id"),
                              ("items","products","product_id"),("payments","orders","order_id"),
                              ("reviews","orders","order_id")]:
        add(table+"."+key+".unmatched","SELECT COUNT(*) FROM stg_"+table+
            " x LEFT JOIN stg_"+parent+" p USING("+key+") WHERE p."+key+" IS NULL")
    add("products.missing_category","SELECT COUNT(*) FROM stg_products WHERE product_category_name "
        "IS NULL","warning","Retained in UNKNOWN.")
    add("products.untranslated_category","SELECT COUNT(*) FROM stg_products p LEFT JOIN "
        "stg_category_translation t USING(product_category_name) WHERE p.product_category_name "
        "IS NOT NULL AND t.product_category_name IS NULL","warning","Original category preserved.")
    dates = {"orders":["order_approved_at","order_delivered_carrier_date",
                      "order_delivered_customer_date","order_estimated_delivery_date"],
             "reviews":["review_creation_date","review_answer_timestamp"],"items":["shipping_limit_date"]}
    for table, columns in dates.items():
        for col in columns:
            add(table+"."+col+".invalid_timestamp","SELECT COUNT(*) FROM stg_"+table+
                " WHERE "+col+" IS NULL AND NULLIF(TRIM("+col+"_raw),'') IS NOT NULL","warning")
    return checks

def check_models(c):
    specs = [
      ("fact_orders.row_count","SELECT (SELECT COUNT(*) FROM fact_orders)-(SELECT COUNT(*) FROM stg_orders)","error"),
      ("fact_orders.key_unique","SELECT COUNT(*)-COUNT(DISTINCT order_id) FROM fact_orders","error"),
      ("fact_order_items.row_count","SELECT (SELECT COUNT(*) FROM fact_order_items)-(SELECT COUNT(*) FROM stg_items)","error"),
      ("fact_order_items.key_unique","SELECT COUNT(*)-COUNT(DISTINCT (order_id,order_item_id)) FROM fact_order_items","error"),
      ("delivered.merchandise_missing","SELECT COUNT(*) FROM fact_orders WHERE order_status='delivered' AND (item_count=0 OR merchandise_value IS NULL)","error"),
      ("merchandise.items_to_orders","SELECT COALESCE((SELECT SUM(price) FROM stg_items),0)-COALESCE((SELECT SUM(merchandise_value) FROM fact_orders),0)","error"),
      ("merchandise.items_to_enriched_items","SELECT COALESCE((SELECT SUM(price) FROM stg_items),0)-COALESCE((SELECT SUM(price) FROM fact_order_items),0)","error"),
      ("merchandise.delivered_grain","SELECT COALESCE((SELECT SUM(price) FROM fact_order_items WHERE order_status='delivered'),0)-COALESCE((SELECT SUM(merchandise_value) FROM fact_orders WHERE order_status='delivered'),0)","error"),
      ("delivery.invalid_flag","SELECT COUNT(*) FROM fact_orders WHERE is_late IS NOT NULL AND NOT delivery_eligible","error"),
      ("delivery.missing_or_invalid","SELECT COUNT(*) FROM fact_orders WHERE order_status='delivered' AND NOT delivery_eligible","warning"),
      ("delivery.invalid_sequence","SELECT COUNT(*) FROM fact_orders WHERE order_status='delivered' AND delivered_timestamp<purchase_timestamp","warning"),
      ("delivered.missing_payment","SELECT COUNT(*) FROM fact_orders WHERE order_status='delivered' AND payment_value IS NULL","warning"),
      ("payment.reconciliation_difference","SELECT COUNT(*) FROM fact_orders WHERE payment_value IS NOT NULL AND merchandise_value IS NOT NULL AND freight_value IS NOT NULL AND payment_value<>merchandise_value+freight_value","warning"),
      ("payment.reconciliation_difference_gt_cent","SELECT COUNT(*) FROM fact_orders WHERE ABS(payment_value-merchandise_value-freight_value)>0.01","warning"),
      ("reviews.multiple_orders","SELECT COUNT(*) FROM (SELECT order_id FROM stg_reviews GROUP BY order_id HAVING COUNT(*)>1)","warning"),
      ("reviews.missing_or_invalid","SELECT COUNT(*) FROM fact_orders WHERE order_status='delivered' AND NOT review_eligible","warning"),
      ("reviews.before_delivery","SELECT COUNT(*) FROM fact_orders WHERE delivery_eligible AND review_eligible AND review_before_delivery","warning"),
    ]
    return [_rec(name,c.execute(sql).fetchone()[0],severity) for name,sql,severity in specs]

def check_analyses(c, analyses):
    """Reconcile actual exported records against independently aggregated facts.

    Does not execute the business queries again. Partial boundary months are
    supported and their flags checked. The Q02 residual is recomputed from
    exported contributions rather than trusting its reported residual column.
    """
    checks = []
    records = {}
    for number in (1, 2, 3):
        matches = [value for name, value in analyses.items()
                   if name.startswith(f"q{number:02}_")]
        checks.append(_rec(f"analysis.q{number:02}.result_count", abs(len(matches)-1)))
        records[number] = matches[0].get("records", []) if len(matches) == 1 else []

    expected_total = c.execute("SELECT COALESCE(SUM(merchandise_value),0) "
        "FROM fact_orders CROSS JOIN analysis_config "
        "WHERE order_status='delivered' AND purchase_date BETWEEN analysis_start AND analysis_end").fetchone()[0]
    expected_rows = c.execute("""
        WITH months AS (
            SELECT CAST(m AS DATE) AS purchase_month, analysis_start, analysis_end
            FROM analysis_config,
                LATERAL GENERATE_SERIES(DATE_TRUNC('month',analysis_start),
                    DATE_TRUNC('month',analysis_end),INTERVAL '1 month') dates(m)
        )
        SELECT m.purchase_month,COALESCE(SUM(f.merchandise_value),0),
            m.analysis_start<=m.purchase_month AND m.analysis_end>=LAST_DAY(m.purchase_month)
        FROM months m LEFT JOIN fact_orders f
            ON f.purchase_month=m.purchase_month AND f.order_status='delivered'
            AND f.purchase_date BETWEEN m.analysis_start AND m.analysis_end
        GROUP BY m.purchase_month,m.analysis_start,m.analysis_end ORDER BY m.purchase_month
        """).fetchall()
    expected_months = {day.isoformat(): (amount, complete) for day, amount, complete in expected_rows}

    def month_key(value):
        return value.isoformat() if hasattr(value, "isoformat") else str(value)

    def amount(value):
        return None if value is None else Decimal(str(value))

    def total(rows):
        values = [amount(row.get("merchandise_value")) for row in rows]
        return None if any(value is None for value in values) else sum(values, Decimal("0"))

    q1_total = total(records[1])
    q3_total = total([row for row in records[3] if row.get("period") == "WINDOW"])
    for number, actual in ((1, q1_total), (3, q3_total)):
        difference = None if actual is None else abs(actual - expected_total)
        checks.append(_rec(f"analysis.q{number:02}.window_merchandise", difference))

    for number in (1, 3):
        rows = records[number] if number == 1 else [row for row in records[3] if row.get("period") == "MONTH"]
        grouped = {}
        for row in rows:
            grouped.setdefault(month_key(row.get("purchase_month")), []).append(row)
        mismatches = 0
        for key in set(expected_months) | set(grouped):
            expected = expected_months.get(key, (None, None))[0]
            actual = total(grouped[key]) if key in grouped else (None if number == 1 else Decimal("0"))
            if actual != expected:
                mismatches += 1
        checks.append(_rec(f"analysis.q{number:02}.month_merchandise", mismatches))
        if number == 1:
            duplicates = sum(len(group)-1 for group in grouped.values())
            checks.append(_rec("analysis.q01.month_unique", duplicates))

    incorrect_boundary_flags = sum(
        month_key(row.get("purchase_month")) not in expected_months
        or row.get("complete_calendar_month") != expected_months[month_key(row.get("purchase_month"))][1]
        for row in records[1])
    checks.append(_rec("analysis.q01.month_boundary_flags", incorrect_boundary_flags,
                       note="Partial months are supported; their completeness labels must be accurate."))

    bad_residuals = 0
    for row in records[2]:
        if row.get("average_order_value") is None or row.get("previous_average_order_value") is None:
            continue
        values = [amount(row.get(name)) for name in
                  ("merchandise_change", "order_count_contribution", "average_order_value_contribution")]
        if any(value is None for value in values):
            bad_residuals += 1
            continue
        # A micro-unit rounding removes float representation noise at the exact cent boundary.
        residual = (values[0]-values[1]-values[2]).quantize(Decimal("0.000001"))
        if abs(residual) > Decimal("0.01"):
            bad_residuals += 1
    checks.append(_rec("analysis.q02.decomposition_residual", bad_residuals,
                       note="Independently recomputed; undefined zero-order AOV months excluded; tolerance 0.01."))
    return checks

def summarize_checks(checks):
    blocking = sum(x["severity"]=="error" and not x["passed"] for x in checks)
    return {"status":"failed" if blocking else "passed","blocking_failures":blocking,
            "warnings":sum(x["severity"]=="warning" and not x["passed"] for x in checks),"checks":checks}
