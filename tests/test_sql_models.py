"""SQL business contracts, exercised on hand-calculated synthetic source rows."""

import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import duckdb
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = {
    "orders": "order_id customer_id order_status order_purchase_timestamp order_approved_at order_delivered_carrier_date order_delivered_customer_date order_estimated_delivery_date".split(),
    "items": "order_id order_item_id product_id seller_id shipping_limit_date price freight_value".split(),
    "payments": "order_id payment_sequential payment_type payment_installments payment_value".split(),
    "customers": "customer_id customer_unique_id customer_zip_code_prefix customer_city customer_state".split(),
    "products": "product_id product_category_name product_name_lenght product_description_lenght product_photos_qty product_weight_g product_length_cm product_height_cm product_width_cm".split(),
    "reviews": "review_id order_id review_score review_comment_title review_comment_message review_creation_date review_answer_timestamp".split(),
    "category_translation": "product_category_name product_category_name_english".split(),
}


def create_raw_tables(con, cases):
    """Mirror all seven source schemas, including fields unrelated to each assertion."""
    for name, columns in SCHEMAS.items():
        con.execute(f"CREATE TABLE raw_{name} ({', '.join(c + ' VARCHAR' for c in columns)})")
        rows = [[row.get(c) for c in columns] for row in cases.get(name, [])]
        if rows:
            con.executemany(f"INSERT INTO raw_{name} VALUES ({', '.join('?' for _ in columns)})", rows)


def configure(con, start="2017-01-01", end="2017-04-30", observation="2017-04-30 23:59:59", state_min=100, group_min=30):
    con.execute("CREATE TABLE analysis_config (analysis_start DATE, analysis_end DATE, observation_end TIMESTAMP, min_state_orders INTEGER, min_group_orders INTEGER)")
    con.execute("INSERT INTO analysis_config VALUES (?, ?, ?, ?, ?)", [start, end, observation, state_min, group_min])


def build_models(con):
    paths = [ROOT / "sql/staging/01_staging.sql", ROOT / "sql/models/01_facts.sql", ROOT / "sql/models/02_dimensions.sql"]
    for path in paths:
        assert path.exists(), f"Required SQL model is not implemented: {path.name}"
        con.execute(path.read_text(encoding="utf-8"))


def query(con, number):
    paths = list((ROOT / "sql/analysis").glob(f"q{number:02}_*.sql"))
    assert len(paths) == 1, f"Business query Q{number:02} is not implemented"
    result = con.execute(paths[0].read_text(encoding="utf-8"))
    keys = [c[0] for c in result.description]
    return [dict(zip(keys, row)) for row in result.fetchall()]


@pytest.fixture
def business_db():
    con = duckdb.connect(":memory:")
    cases = json.loads((ROOT / "tests/fixtures/business_cases.json").read_text(encoding="utf-8"))
    create_raw_tables(con, cases)
    configure(con)
    yield con
    con.close()


def test_order_aggregation_does_not_multiply_multiple_children(business_db):
    build_models(business_db)
    row = business_db.execute("SELECT item_count, merchandise_value, freight_value, payment_value FROM fact_orders WHERE order_id='multi'").fetchone()
    assert row == (2, Decimal("150.00"), Decimal("15.00"), Decimal("165.00"))
    assert business_db.execute("SELECT count(*), count(DISTINCT order_id) FROM fact_orders").fetchone() == (6, 6)


def test_latest_review_ties_use_creation_then_id(business_db):
    build_models(business_db)
    assert business_db.execute("SELECT review_score FROM fact_orders WHERE order_id='multi'").fetchone() == (1,)


def test_review_creation_breaks_answer_ties_and_null_answer_is_last(business_db):
    build_models(business_db)
    business_db.execute("INSERT INTO raw_reviews (review_id, order_id, review_score, review_creation_date, review_answer_timestamp) VALUES ('z', 'multi', '4', '2017-01-08', '2017-01-08 10:00:00'), ('null_answer', 'multi', '5', '2017-01-20', NULL)")
    build_models(business_db)
    assert business_db.execute("SELECT review_score FROM fact_orders WHERE order_id='multi'").fetchone() == (4,)


def test_exact_duplicate_source_records_do_not_increase_revenue(business_db):
    build_models(business_db)
    business_db.execute("INSERT INTO raw_items SELECT * FROM raw_items WHERE order_id='multi' AND order_item_id='1'")
    build_models(business_db)
    assert business_db.execute("SELECT item_count, merchandise_value FROM fact_orders WHERE order_id='multi'").fetchone() == (2, Decimal("150.00"))


def test_invalid_delivery_sequence_exits_logistics_only(business_db):
    build_models(business_db)
    business_db.execute("UPDATE raw_orders SET order_delivered_customer_date='2016-12-31', order_estimated_delivery_date='invalid' WHERE order_id='multi'")
    build_models(business_db)
    assert business_db.execute("SELECT merchandise_value, delivery_eligible, delivery_days, is_late FROM fact_orders WHERE order_id='multi'").fetchone() == (Decimal("150.00"), False, None, None)


def test_missing_logistics_keep_revenue_and_unknown_dimensions(business_db):
    build_models(business_db)
    assert business_db.execute("SELECT merchandise_value, delivery_eligible, is_late, delivery_days FROM fact_orders WHERE order_id='missing_dates'").fetchone() == (Decimal("50.00"), False, None, None)
    assert business_db.execute("SELECT category, price FROM fact_order_items WHERE order_id='multi' AND order_item_id=2").fetchone() == ("UNKNOWN", Decimal("50.00"))
    assert business_db.execute("SELECT customer_state FROM fact_orders WHERE order_id='april'").fetchone() == ("UNKNOWN",)


def test_same_calendar_delivery_day_is_not_late(business_db):
    build_models(business_db)
    assert business_db.execute("SELECT is_late, delivery_days FROM fact_orders WHERE order_id='multi'").fetchone() == (False, pytest.approx(4 + 8 / 24))


def test_invalid_amounts_remain_visible_and_missing_items_are_null():
    con = duckdb.connect(":memory:")
    cases = {"orders": [{"order_id":"bad", "order_status":"delivered", "order_purchase_timestamp":"2017-01-01"}, {"order_id":"empty", "order_status":"delivered", "order_purchase_timestamp":"2017-01-01"}], "items": [{"order_id":"bad", "order_item_id":"1", "price":"invalid", "freight_value":"1"}, {"order_id":"bad", "order_item_id":"2", "price":"5", "freight_value":"1"}]}
    create_raw_tables(con, cases)
    configure(con)
    build_models(con)
    assert con.execute("SELECT price, price_raw FROM stg_items WHERE order_item_id=1").fetchone() == (None, "invalid")
    assert con.execute("SELECT order_id, item_count, merchandise_value FROM fact_orders ORDER BY order_id").fetchall() == [("bad", 2, None), ("empty", 0, None)]


def test_month_series_preserves_empty_month_and_zero_denominators(business_db):
    build_models(business_db)
    rows = query(business_db, 1)
    assert [r["purchase_month"] for r in rows] == [date(2017, m, 1) for m in range(1, 5)]
    assert [(r["merchandise_value"], r["delivered_orders"], r["average_order_value"]) for r in rows] == [(Decimal("200.00"), 2, 100), (Decimal("0.00"), 0, None), (Decimal("300.00"), 2, 150), (Decimal("400.00"), 1, 400)]
    assert rows[0]["canceled_orders"] == 1
    assert rows[0]["canceled_order_share"] == pytest.approx(1 / 3)
    assert rows[1]["canceled_order_share"] is None


def test_month_change_and_sequential_revenue_decomposition(business_db):
    build_models(business_db)
    rows = query(business_db, 2)
    assert rows[2]["previous_merchandise_value"] == 0
    assert rows[2]["merchandise_change_rate"] is None
    april = rows[3]
    assert (april["merchandise_change"], april["order_count_contribution"], april["average_order_value_contribution"]) == (100, -150, 250)
    assert april["decomposition_residual"] == pytest.approx(0)
    assert rows[1]["average_order_value_contribution"] is None


def test_category_shares_and_unknown_preserve_total(business_db):
    build_models(business_db)
    rows = query(business_db, 3)
    total = [r for r in rows if r["period"] == "WINDOW"]
    assert sum(r["merchandise_value"] for r in total) == Decimal("900.00")
    unknown = next(r for r in total if r["category"] == "UNKNOWN")
    assert unknown["merchandise_value"] == Decimal("450.00")
    assert unknown["merchandise_share"] == pytest.approx(0.5)


def test_top_ten_categories_include_other_and_nonadditive_order_count():
    con = duckdb.connect(":memory:")
    cases = {"orders":[{"order_id":"many", "order_status":"delivered", "order_purchase_timestamp":"2017-01-01"}], "items":[], "products":[]}
    for number in range(1, 13):
        cases["items"].append({"order_id":"many", "order_item_id":str(number), "product_id":str(number), "price":str(number), "freight_value":"0"})
        cases["products"].append({"product_id":str(number), "product_category_name":f"category_{number:02}"})
    create_raw_tables(con, cases)
    configure(con)
    build_models(con)
    rows = [r for r in query(con, 3) if r["period"] == "WINDOW"]
    assert len(rows) == 11
    assert sum(r["merchandise_value"] for r in rows) == 78
    other = next(r for r in rows if r["category"] == "OTHER")
    assert (other["merchandise_value"], other["containing_category_orders"]) == (3, 1)


def test_state_priority_excludes_small_samples_and_exposes_denominators(business_db):
    build_models(business_db)
    rows = query(business_db, 4)
    sp = next(r for r in rows if r["customer_state"] == "SP")
    assert (sp["delivered_orders"], sp["delivery_eligible_orders"], sp["late_orders"]) == (2, 1, 0)
    assert sp["delivery_coverage"] == pytest.approx(0.5)
    assert all(r["investigation_rank"] is None for r in rows)


def test_duration_quantiles_use_valid_actual_dates(business_db):
    build_models(business_db)
    overall = next(r for r in query(business_db, 5) if r["scope"] == "WINDOW")
    assert (overall["delivered_orders"], overall["duration_eligible_orders"]) == (5, 4)
    assert overall["median_delivery_days"] == pytest.approx(6.5)
    assert overall["p90_delivery_days"] == pytest.approx(8.7)


def test_actual_delivery_without_estimate_still_enters_duration_sample(business_db):
    build_models(business_db)
    business_db.execute("UPDATE raw_orders SET order_estimated_delivery_date=NULL WHERE order_id='multi'")
    build_models(business_db)
    assert business_db.execute("SELECT delivery_days, delivery_eligible, is_late FROM fact_orders WHERE order_id='multi'").fetchone() == (pytest.approx(4 + 8 / 24), False, None)
    overall = next(r for r in query(business_db, 5) if r["scope"] == "WINDOW")
    assert overall["duration_eligible_orders"] == 4


def test_late_coverage_is_month_and_state_specific(business_db):
    build_models(business_db)
    rows = query(business_db, 6)
    sp_jan = next(r for r in rows if r["purchase_month"] == date(2017, 1, 1) and r["customer_state"] == "SP")
    assert (sp_jan["delivered_orders"], sp_jan["delivery_eligible_orders"], sp_jan["joint_eligible_orders"]) == (2, 1, 1)
    assert sp_jan["late_share"] == 0
    assert sp_jan["joint_coverage"] == pytest.approx(0.5)


def test_review_distribution_uses_joint_delivery_review_sample(business_db):
    build_models(business_db)
    rows = query(business_db, 7)
    late = next(r for r in rows if r["delivery_group"] == "LATE")
    on_time = next(r for r in rows if r["delivery_group"] == "ON_TIME")
    assert (late["joint_eligible_orders"], late["low_score_orders"], late["score_5_orders"]) == (2, 1, 1)
    assert late["low_score_share"] == pytest.approx(0.5)
    assert (on_time["joint_eligible_orders"], on_time["low_score_orders"]) == (2, 2)


def test_missing_or_invalid_review_is_not_in_joint_sample(business_db):
    build_models(business_db)
    business_db.execute("UPDATE raw_reviews SET review_score='6' WHERE order_id='april'")
    build_models(business_db)
    april = next(r for r in query(business_db, 6) if r["purchase_month"] == date(2017, 4, 1) and r["customer_state"] == "UNKNOWN")
    assert (april["delivery_eligible_orders"], april["review_eligible_orders"], april["joint_eligible_orders"]) == (1, 0, 0)
    late = next(r for r in query(business_db, 7) if r["delivery_group"] == "LATE")
    assert (late["joint_eligible_orders"], late["low_score_orders"], late["low_score_share"]) == (1, 1, 1)


def test_fractional_review_score_is_not_rounded_into_valid_rating(business_db):
    business_db.execute("UPDATE raw_reviews SET review_score='1.5' WHERE order_id='april'")
    build_models(business_db)
    assert business_db.execute("SELECT review_score, review_eligible FROM fact_orders WHERE order_id='april'").fetchone() == (None, False)


def test_state_and_group_thresholds_use_configured_sample_counts(business_db):
    build_models(business_db)
    business_db.execute("UPDATE analysis_config SET min_state_orders=2, min_group_orders=1")
    state_rows = query(business_db, 4)
    assert next(r for r in state_rows if r["customer_state"] == "RJ")["investigation_rank"] == 1
    assert next(r for r in state_rows if r["customer_state"] == "SP")["investigation_rank"] == 2
    assert next(r for r in state_rows if r["customer_state"] == "UNKNOWN")["investigation_rank"] is None
    march = next(r for r in query(business_db, 8) if r["purchase_month"] == date(2017, 3, 1) and r["customer_state"] == "RJ" and r["sample"] == "ALL_JOINT")
    assert march["meets_group_threshold"] is True
    assert march["low_score_share_gap"] == 0


def test_stratified_review_comparison_exposes_early_answer_sensitivity(business_db):
    build_models(business_db)
    rows = query(business_db, 8)
    march = [r for r in rows if r["purchase_month"] == date(2017, 3, 1) and r["customer_state"] == "RJ"]
    all_sample = next(r for r in march if r["sample"] == "ALL_JOINT")
    sensitivity = next(r for r in march if r["sample"] == "EXCLUDE_EARLY_ANSWERS")
    assert (all_sample["on_time_orders"], all_sample["late_orders"], all_sample["early_answer_orders"]) == (1, 1, 1)
    assert (sensitivity["on_time_orders"], sensitivity["late_orders"], sensitivity["low_score_share_gap"]) == (0, 1, None)
    assert not all_sample["meets_group_threshold"]


def test_missing_review_answer_retains_joint_sample_and_exposes_coverage(business_db):
    build_models(business_db)
    row = next(r for r in query(business_db, 8) if r["purchase_month"] == date(2017, 4, 1) and r["customer_state"] == "UNKNOWN" and r["sample"] == "EXCLUDE_EARLY_ANSWERS")
    assert (row["late_orders"], row["answer_timestamp_orders"], row["answer_timestamp_coverage"]) == (1, 0, 0)


def test_monthly_category_change_preserves_complete_month_baseline(business_db):
    build_models(business_db)
    rows = [r for r in query(business_db, 3) if r["period"] == "MONTH"]
    march_books = next(r for r in rows if r["purchase_month"] == date(2017, 3, 1) and r["category"] == "books")
    assert (march_books["previous_merchandise_value"], march_books["merchandise_change"], march_books["change_contribution_share"]) == (0, 200, pytest.approx(2 / 3))
    april_unknown = next(r for r in rows if r["purchase_month"] == date(2017, 4, 1) and r["category"] == "UNKNOWN")
    assert april_unknown["merchandise_change"] == 400
    assert sum(r["merchandise_value"] for r in rows if r["purchase_month"] == date(2017, 4, 1)) == 400


def cohort_db():
    con = duckdb.connect(":memory:")
    order_specs = [
        ("a0", "a_old", "a", "2016-12-15 10:00:00"),
        ("a1", "a_new", "a", "2017-01-14 10:00:00"),
        ("b0", "b_old", "b", "2017-01-01 10:00:00"),
        ("b_equal", "b_equal_customer", "b", "2017-01-01 10:00:00"),
        ("b30", "b_new", "b", "2017-01-31 10:00:00"),
        ("b31", "b_third", "b", "2017-02-01 10:00:00"),
        ("c0", "c_old", "c", "2017-01-01 10:00:00"),
        ("c31", "c_new", "c", "2017-02-01 10:00:00"),
        ("d0", "d", "d", "2017-04-10 10:00:00"),
        ("e0", "e", "e", "2017-03-31 23:59:59"),
        ("future", "future", "f", "2017-05-10 10:00:00"),
        ("d_future", "d_new", "d", "2017-05-01 10:00:00"),
    ]
    cases = {"orders": [], "customers": [], "items": []}
    for order, customer, unique, purchase in order_specs:
        cases["orders"].append({"order_id": order, "customer_id":customer, "order_status":"delivered", "order_purchase_timestamp":purchase})
        cases["customers"].append({"customer_id":customer, "customer_unique_id":unique, "customer_state":"SP"})
        cases["items"].append({"order_id":order, "order_item_id":"1", "price":"1.00", "freight_value":"0.00"})
    create_raw_tables(con, cases)
    configure(con)
    build_models(con)
    return con


def test_first_observed_purchase_uses_all_source_and_strictly_later_order():
    con = cohort_db()
    rows = {r["customer_unique_id"]: r for r in query(con, 9)}
    assert rows["a"]["first_purchase_timestamp"] == datetime(2016, 12, 15, 10)
    assert rows["b"]["first_order_id"] == "b0"
    assert rows["b"]["simultaneous_additional_orders"] == 1
    assert rows["b"]["next_purchase_timestamp"] == datetime(2017, 1, 31, 10)
    assert rows["b"]["days_to_next_purchase"] == 30
    assert rows["b"]["repeat_within_30_days"] is True
    assert rows["c"]["days_to_next_purchase"] == 31
    assert rows["c"]["repeat_within_30_days"] is False
    assert rows["d"]["next_purchase_timestamp"] is None
    assert "f" not in rows


def test_cohort_maturity_and_boundary_do_not_use_future_purchase_data():
    con = cohort_db()
    rows = {r["cohort_month"]: r for r in query(con, 10)}
    january = rows[date(2017, 1, 1)]
    assert (january["total_customers"], january["eligible_customers"], january["repeat_customers_30d"], january["repeat_share_30d"]) == (2, 2, 1, 0.5)
    march = rows[date(2017, 3, 1)]
    assert (march["total_customers"], march["eligible_customers"]) == (1, 1)
    april = rows[date(2017, 4, 1)]
    assert (april["total_customers"], april["eligible_customers"], april["immature_customers"], april["repeat_share_30d"]) == (1, 0, 1, None)
    assert date(2016, 12, 1) not in rows
    assert rows[date(2017, 2, 1)]["repeat_share_30d"] is None


def test_configurable_window_clips_business_queries_but_not_customer_first():
    con = cohort_db()
    con.execute("UPDATE analysis_config SET analysis_start='2017-02-01', analysis_end='2017-03-31', observation_end='2017-03-31 23:59:59'")
    rows = query(con, 1)
    assert [(r["purchase_month"], r["delivered_orders"]) for r in rows] == [(date(2017, 2, 1), 2), (date(2017, 3, 1), 1)]
    customers = {r["customer_unique_id"]:r for r in query(con, 9)}
    assert customers["a"]["first_purchase_timestamp"] == datetime(2016, 12, 15, 10)
    assert "d" not in customers


def test_partial_mature_cohort_exposes_total_and_eligible_customers():
    con = cohort_db()
    con.execute("INSERT INTO raw_orders (order_id, customer_id, order_status, order_purchase_timestamp) VALUES ('g0', 'g', 'delivered', '2017-03-31 23:59:59.500')")
    con.execute("INSERT INTO raw_customers (customer_id, customer_unique_id, customer_state) VALUES ('g', 'g', 'SP')")
    con.execute("INSERT INTO raw_items (order_id, order_item_id, price, freight_value) VALUES ('g0', '1', '1', '0')")
    build_models(con)
    march = next(r for r in query(con, 10) if r["cohort_month"] == date(2017, 3, 1))
    assert (march["total_customers"], march["eligible_customers"], march["immature_customers"], march["observation_coverage"]) == (2, 1, 1, 0.5)


def test_repeat_thirty_days_plus_one_second_is_outside_window():
    con = cohort_db()
    con.execute("UPDATE raw_orders SET order_purchase_timestamp='2017-01-31 10:00:01' WHERE order_id='c31'")
    build_models(con)
    customer = next(r for r in query(con, 9) if r["customer_unique_id"] == "c")
    assert customer["repeat_within_30_days"] is False
