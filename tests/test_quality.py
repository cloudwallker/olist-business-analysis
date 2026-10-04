"""Quality gates must catch corruption even when row counts and money stay unchanged."""

from pathlib import Path

import pytest

from olist_analytics import quality
from test_sql_models import ROOT, build_models, business_db


@pytest.fixture
def quality_db(business_db):
    build_models(business_db)
    return business_db


def checks_by_name(checks):
    return {check["check"]: check for check in checks}


def analysis_checks(con, sql_dir=None):
    assert hasattr(quality, "check_analyses"), "Independent SQL result reconciliation is not implemented"
    analyses = {}
    for path in (sql_dir or ROOT / "sql/analysis").glob("q*.sql"):
        cursor = con.execute(path.read_text(encoding="utf-8"))
        columns = [c[0] for c in cursor.description]
        rows = cursor.fetchall()
        analyses[path.stem] = {"rows": len(rows), "columns": columns,
            "records": [dict(zip(columns, row)) for row in rows]}
    return checks_by_name(quality.check_analyses(con, analyses))


def redirected_sql(tmp_path, query_number, wrapper):
    """Run changed real SQL files; do not mock DuckDB or the reconciliation outputs."""
    for path in (ROOT / "sql/analysis").glob("q*.sql"):
        text = path.read_text(encoding="utf-8")
        if path.name.startswith(f"q{query_number:02}_"):
            text = wrapper.replace("{query}", text.strip().rstrip(";"))
        (tmp_path / path.name).write_text(text, encoding="utf-8")
    return tmp_path


def test_fact_item_duplicate_composite_key_blocks_same_count_same_money(quality_db):
    quality_db.execute("UPDATE fact_order_items SET order_item_id=1 WHERE order_id='multi'")
    checks = checks_by_name(quality.check_models(quality_db))
    assert "fact_order_items.key_unique" in checks, "Fact item composite-key gate is missing"
    assert checks["fact_order_items.row_count"]["passed"] is True
    assert checks["merchandise.items_to_enriched_items"]["passed"] is True
    assert checks["fact_order_items.key_unique"]["value"] == 1
    assert quality.summarize_checks(list(checks.values()))["status"] == "failed"


def test_real_queries_reconcile_hand_checked_window_and_month_totals(quality_db):
    checks = analysis_checks(quality_db)
    assert set(checks) >= {
        "analysis.q01.window_merchandise", "analysis.q03.window_merchandise",
        "analysis.q01.month_merchandise", "analysis.q03.month_merchandise",
        "analysis.q02.decomposition_residual",
    }
    assert all(check["passed"] for check in checks.values())


def test_q01_wrong_month_money_blocks_window_and_month_gates(quality_db, tmp_path):
    analysis_checks(quality_db)
    sql_dir = redirected_sql(tmp_path, 1,
        "SELECT * REPLACE (merchandise_value + 1 AS merchandise_value) FROM ({query})")
    checks = analysis_checks(quality_db, sql_dir)
    assert checks["analysis.q01.window_merchandise"]["value"] == 4
    assert checks["analysis.q01.month_merchandise"]["value"] == 4
    assert checks["analysis.q03.window_merchandise"]["passed"] is True
    assert quality.summarize_checks(list(checks.values()))["status"] == "failed"


def test_q03_missing_one_month_category_is_detected_despite_correct_window(quality_db, tmp_path):
    analysis_checks(quality_db)
    sql_dir = redirected_sql(tmp_path, 3,
        "SELECT * FROM ({query}) WHERE NOT (period='MONTH' AND category='UNKNOWN' AND purchase_month=DATE '2017-04-01')")
    checks = analysis_checks(quality_db, sql_dir)
    assert checks["analysis.q03.window_merchandise"]["passed"] is True
    assert checks["analysis.q03.month_merchandise"]["value"] == 1


def test_q03_other_remainder_is_required_for_top_ten_reconciliation(quality_db, tmp_path):
    for number in range(1, 13):
        quality_db.execute("INSERT INTO raw_products (product_id,product_category_name) VALUES (?,?)", [f"p{number}",f"category_{number}"])
        quality_db.execute("INSERT INTO raw_items (order_id,order_item_id,product_id,price,freight_value) VALUES ('april',?,?,?, '0')", [str(number+1),f"p{number}",str(number)])
    build_models(quality_db)
    assert all(c["passed"] for c in analysis_checks(quality_db).values())
    sql_dir = redirected_sql(tmp_path, 3, "SELECT * FROM ({query}) WHERE category <> 'OTHER'")
    checks = analysis_checks(quality_db, sql_dir)
    assert checks["analysis.q03.window_merchandise"]["passed"] is False
    assert checks["analysis.q03.month_merchandise"]["passed"] is False


@pytest.mark.parametrize("difference, expected_failures", [("0.01", 0), ("0.02", 1)])
def test_q02_residual_recomputed_from_contributions_and_cent_tolerance(quality_db, tmp_path, difference, expected_failures):
    analysis_checks(quality_db)
    sql_dir = redirected_sql(tmp_path, 2,
        f"SELECT * REPLACE (order_count_contribution + {difference} AS order_count_contribution) FROM ({{query}}) WHERE purchase_month=DATE '2017-04-01'")
    checks = analysis_checks(quality_db, sql_dir)
    # Reported decomposition_residual remains zero; the gate must independently recompute it.
    assert checks["analysis.q02.decomposition_residual"]["value"] == expected_failures


def test_partial_months_are_supported_and_boundary_flags_are_verified(quality_db, tmp_path):
    quality_db.execute("UPDATE analysis_config SET analysis_start='2017-01-02', analysis_end='2017-04-15'")
    assert all(c["passed"] for c in analysis_checks(quality_db).values())
    sql_dir = redirected_sql(tmp_path, 1,
        "SELECT * REPLACE (TRUE AS complete_calendar_month) FROM ({query})")
    assert analysis_checks(quality_db, sql_dir)["analysis.q01.month_boundary_flags"]["value"] == 2
