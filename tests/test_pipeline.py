import csv
import hashlib
import json
from pathlib import Path

import pytest

from olist_analytics.pipeline import PipelineError, load_current, run_pipeline


HEADERS = {
    "orders": "order_id,customer_id,order_status,order_purchase_timestamp,order_approved_at,order_delivered_carrier_date,order_delivered_customer_date,order_estimated_delivery_date",
    "items": "order_id,order_item_id,product_id,seller_id,shipping_limit_date,price,freight_value",
    "payments": "order_id,payment_sequential,payment_type,payment_installments,payment_value",
    "customers": "customer_id,customer_unique_id,customer_zip_code_prefix,customer_city,customer_state",
    "products": "product_id,product_category_name,product_name_lenght,product_description_lenght,product_photos_qty,product_weight_g,product_length_cm,product_height_cm,product_width_cm",
    "reviews": "review_id,order_id,review_score,review_comment_title,review_comment_message,review_creation_date,review_answer_timestamp",
    "category_translation": "product_category_name,product_category_name_english",
}
FILES = {
    name: ("product_category_name_translation.csv" if name == "category_translation"
           else "olist_order_items_dataset.csv" if name == "items"
           else "olist_order_payments_dataset.csv" if name == "payments"
           else "olist_order_reviews_dataset.csv" if name == "reviews"
           else "olist_" + name + "_dataset.csv")
    for name in HEADERS
}
CONFIG = {
    "analysis_start": "2017-02-01", "analysis_end": "2017-02-28",
    "observation_end": "2017-03-31 23:59:59",
    "min_state_orders": 100, "min_group_orders": 30,
}


def write_inputs(raw_dir):
    raw_dir.mkdir(parents=True)
    rows = {
        "orders": [dict(order_id="first", customer_id="c1", order_status="delivered",
                        order_purchase_timestamp="2017-02-05 10:00:00",
                        order_delivered_customer_date="2017-02-10 18:00:00",
                        order_estimated_delivery_date="2017-02-10 00:00:00")],
        "items": [dict(order_id="first", order_item_id="1", product_id="p1",
                       seller_id="s1", price="100.00", freight_value="10.00")],
        "payments": [dict(order_id="first", payment_sequential="1",
                          payment_type="credit_card", payment_installments="1",
                          payment_value="110.00")],
        "customers": [dict(customer_id="c1", customer_unique_id="unique1",
                           customer_state="SP", customer_city="sample")],
        "products": [dict(product_id="p1", product_category_name="livros")],
        "reviews": [dict(review_id="r1", order_id="first", review_score="2",
                         review_creation_date="2017-02-11",
                         review_answer_timestamp="2017-02-12 10:00:00")],
        "category_translation": [dict(product_category_name="livros",
                                      product_category_name_english="books")],
    }
    for name, header in HEADERS.items():
        with (raw_dir / FILES[name]).open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=header.split(","))
            writer.writeheader()
            writer.writerows(rows[name])
    return raw_dir


def csv_hashes(run_dir):
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (run_dir / "csv").glob("*.csv")}


def test_missing_input_is_actionable_and_never_publishes(tmp_path):
    with pytest.raises(PipelineError, match="olist_orders_dataset.csv"):
        run_pipeline(tmp_path / "missing", tmp_path / "build", CONFIG)
    assert not (tmp_path / "build" / "current.json").exists()


def test_invalid_config_is_rejected_before_publishing(tmp_path):
    raw = write_inputs(tmp_path / "raw")
    config = dict(CONFIG, analysis_end="2017-01-01")
    with pytest.raises(PipelineError, match="analysis_start"):
        run_pipeline(raw, tmp_path / "build", config)
    assert not (tmp_path / "build" / "current.json").exists()


def test_real_exports_are_stable_across_rebuilds(tmp_path):
    raw = write_inputs(tmp_path / "raw")
    result = run_pipeline(raw, tmp_path / "build", CONFIG)
    first = load_current(tmp_path / "build")
    assert result["status"] == "passed"
    assert result["quality"]["blocking_failures"] == 0
    assert (first / "warehouse.duckdb").is_file()
    hashes = csv_hashes(first)
    assert "fact_orders.csv" in hashes and len(hashes) >= 15
    run_pipeline(raw, tmp_path / "build", CONFIG)
    assert csv_hashes(load_current(tmp_path / "build")) == hashes


def test_failed_data_check_retains_previous_current(tmp_path):
    raw = write_inputs(tmp_path / "raw")
    run_pipeline(raw, tmp_path / "build", CONFIG)
    previous = (tmp_path / "build" / "current.json").read_bytes()
    items = raw / FILES["items"]
    items.write_text(HEADERS["items"] + "\n", encoding="utf-8")
    with pytest.raises(PipelineError, match="merchandise"):
        run_pipeline(raw, tmp_path / "build", CONFIG)
    assert (tmp_path / "build" / "current.json").read_bytes() == previous
    failed = list((tmp_path / "build" / "runs").glob("*/failed.json"))
    assert failed
    failed_quality = json.loads((failed[-1].parent / "quality.json").read_text(encoding="utf-8"))
    assert failed_quality["status"] == "failed"
    assert failed_quality["blocking_failures"] > 0


def test_conflicting_order_key_is_blocked(tmp_path):
    raw = write_inputs(tmp_path / "raw")
    path = raw / FILES["orders"]
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    with path.open("a", encoding="utf-8", newline="") as stream:
        csv.DictWriter(stream, fieldnames=HEADERS["orders"].split(",")).writerow(
            dict(rows[0], order_status="canceled"))
    with pytest.raises(PipelineError, match="key"):
        run_pipeline(raw, tmp_path / "build", CONFIG)


def test_missing_source_column_is_not_silently_inferred(tmp_path):
    raw = write_inputs(tmp_path / "raw")
    (raw / FILES["items"]).write_text("order_id,order_item_id,product_id\nfirst,1,p1\n",
                                    encoding="utf-8")
    with pytest.raises(PipelineError, match="price"):
        run_pipeline(raw, tmp_path / "build", CONFIG)


def test_current_pointer_cannot_escape_build_directory(tmp_path):
    (tmp_path / "current.json").write_text(json.dumps({"run_id": "../../outside"}))
    with pytest.raises(PipelineError, match="pointer"):
        load_current(tmp_path)
