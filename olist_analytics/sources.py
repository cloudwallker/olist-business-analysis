import csv
import hashlib
from pathlib import Path

SOURCE_URL = "https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce"
ARCHIVE_SHA256 = "967e41e04fc306fe604e2a693f488995a8b41e5047418f8a5c8e4abd6deca784"
SOURCES = {
 "orders": ("olist_orders_dataset.csv","order_id,customer_id,order_status,order_purchase_timestamp,order_approved_at,order_delivered_carrier_date,order_delivered_customer_date,order_estimated_delivery_date"),
 "items": ("olist_order_items_dataset.csv","order_id,order_item_id,product_id,seller_id,shipping_limit_date,price,freight_value"),
 "payments": ("olist_order_payments_dataset.csv","order_id,payment_sequential,payment_type,payment_installments,payment_value"),
 "customers": ("olist_customers_dataset.csv","customer_id,customer_unique_id,customer_zip_code_prefix,customer_city,customer_state"),
 "products": ("olist_products_dataset.csv","product_id,product_category_name,product_name_lenght,product_description_lenght,product_photos_qty,product_weight_g,product_length_cm,product_height_cm,product_width_cm"),
 "reviews": ("olist_order_reviews_dataset.csv","review_id,order_id,review_score,review_comment_title,review_comment_message,review_creation_date,review_answer_timestamp"),
 "category_translation": ("product_category_name_translation.csv","product_category_name,product_category_name_english"),
}

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1048576), b""):
            digest.update(block)
    return digest.hexdigest()

def load_raw(connection, raw_dir: Path) -> dict:
    manifest = {"expected_dataset":"Olist version 2", "source_url":SOURCE_URL,
                "license":"CC BY-NC-SA 4.0", "files":[]}
    for name, (filename, required) in SOURCES.items():
        path = raw_dir / filename
        if not path.is_file():
            raise ValueError("Missing required source file: " + filename)
        with path.open(encoding="utf-8-sig", newline="") as stream:
            headers = next(csv.reader(stream), [])
        missing = sorted(set(required.split(",")) - set(headers))
        if missing:
            raise ValueError(filename + " missing columns: " + ", ".join(missing))
        if len(headers) != len(set(headers)):
            raise ValueError(filename + " has duplicate headers")
        connection.execute("CREATE TABLE raw_" + name + " AS SELECT * FROM read_csv(?, "
                           "header=true, all_varchar=true, sample_size=-1, strict_mode=true)",
                           [str(path.resolve())])
        manifest["files"].append({"filename":filename, "sha256":sha256_file(path),
            "rows":connection.execute("SELECT COUNT(*) FROM raw_" + name).fetchone()[0],
            "columns":headers})
    return manifest

