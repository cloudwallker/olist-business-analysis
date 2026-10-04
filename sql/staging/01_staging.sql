-- 业务问题：可靠地将源字符串转换为可分析类型，保留原值供质量审查。
-- 输入/输出粒度：各源表完整记录；仅去完全相同的重复，不覆盖业务键冲突。
-- 过滤：不按业务窗口或缺失字段删行。限制：TRY_CAST失败保留NULL和*_raw；质量层必须阻止关键异常发布。
CREATE OR REPLACE TABLE stg_orders AS
SELECT DISTINCT
    NULLIF(TRIM(order_id), '') AS order_id,
    NULLIF(TRIM(customer_id), '') AS customer_id,
    NULLIF(TRIM(order_status), '') AS order_status,
    TRY_CAST(order_purchase_timestamp AS TIMESTAMP) AS order_purchase_timestamp,
    TRY_CAST(order_approved_at AS TIMESTAMP) AS order_approved_at,
    TRY_CAST(order_delivered_carrier_date AS TIMESTAMP) AS order_delivered_carrier_date,
    TRY_CAST(order_delivered_customer_date AS TIMESTAMP) AS order_delivered_customer_date,
    TRY_CAST(order_estimated_delivery_date AS TIMESTAMP) AS order_estimated_delivery_date,
    order_id AS order_id_raw, customer_id AS customer_id_raw, order_status AS order_status_raw,
    order_purchase_timestamp AS order_purchase_timestamp_raw, order_approved_at AS order_approved_at_raw,
    order_delivered_carrier_date AS order_delivered_carrier_date_raw,
    order_delivered_customer_date AS order_delivered_customer_date_raw,
    order_estimated_delivery_date AS order_estimated_delivery_date_raw
FROM raw_orders;

CREATE OR REPLACE TABLE stg_items AS
SELECT DISTINCT
    NULLIF(TRIM(order_id), '') AS order_id,
    TRY_CAST(order_item_id AS INTEGER) AS order_item_id,
    NULLIF(TRIM(product_id), '') AS product_id,
    NULLIF(TRIM(seller_id), '') AS seller_id,
    TRY_CAST(shipping_limit_date AS TIMESTAMP) AS shipping_limit_date,
    TRY_CAST(price AS DECIMAL(18,2)) AS price,
    TRY_CAST(freight_value AS DECIMAL(18,2)) AS freight_value,
    order_id AS order_id_raw, order_item_id AS order_item_id_raw, product_id AS product_id_raw,
    seller_id AS seller_id_raw, shipping_limit_date AS shipping_limit_date_raw,
    price AS price_raw, freight_value AS freight_value_raw
FROM raw_items;

CREATE OR REPLACE TABLE stg_payments AS
SELECT DISTINCT
    NULLIF(TRIM(order_id), '') AS order_id,
    TRY_CAST(payment_sequential AS INTEGER) AS payment_sequential,
    NULLIF(TRIM(payment_type), '') AS payment_type,
    TRY_CAST(payment_installments AS INTEGER) AS payment_installments,
    TRY_CAST(payment_value AS DECIMAL(18,2)) AS payment_value,
    order_id AS order_id_raw, payment_sequential AS payment_sequential_raw,
    payment_type AS payment_type_raw, payment_installments AS payment_installments_raw,
    payment_value AS payment_value_raw
FROM raw_payments;

CREATE OR REPLACE TABLE stg_customers AS
SELECT DISTINCT
    NULLIF(TRIM(customer_id), '') AS customer_id,
    NULLIF(TRIM(customer_unique_id), '') AS customer_unique_id,
    NULLIF(TRIM(customer_zip_code_prefix), '') AS customer_zip_code_prefix,
    NULLIF(TRIM(customer_city), '') AS customer_city,
    COALESCE(NULLIF(TRIM(customer_state), ''), 'UNKNOWN') AS customer_state,
    customer_id AS customer_id_raw, customer_unique_id AS customer_unique_id_raw,
    customer_zip_code_prefix AS customer_zip_code_prefix_raw, customer_city AS customer_city_raw,
    customer_state AS customer_state_raw
FROM raw_customers;

CREATE OR REPLACE TABLE stg_products AS
SELECT DISTINCT
    NULLIF(TRIM(product_id), '') AS product_id,
    NULLIF(TRIM(product_category_name), '') AS product_category_name,
    TRY_CAST(product_name_lenght AS INTEGER) AS product_name_lenght,
    TRY_CAST(product_description_lenght AS INTEGER) AS product_description_lenght,
    TRY_CAST(product_photos_qty AS INTEGER) AS product_photos_qty,
    TRY_CAST(product_weight_g AS DOUBLE) AS product_weight_g,
    TRY_CAST(product_length_cm AS DOUBLE) AS product_length_cm,
    TRY_CAST(product_height_cm AS DOUBLE) AS product_height_cm,
    TRY_CAST(product_width_cm AS DOUBLE) AS product_width_cm,
    product_id AS product_id_raw, product_category_name AS product_category_name_raw,
    product_name_lenght AS product_name_lenght_raw, product_description_lenght AS product_description_lenght_raw,
    product_photos_qty AS product_photos_qty_raw, product_weight_g AS product_weight_g_raw,
    product_length_cm AS product_length_cm_raw, product_height_cm AS product_height_cm_raw,
    product_width_cm AS product_width_cm_raw
FROM raw_products;

CREATE OR REPLACE TABLE stg_reviews AS
SELECT DISTINCT
    NULLIF(TRIM(review_id), '') AS review_id,
    NULLIF(TRIM(order_id), '') AS order_id,
    CASE WHEN REGEXP_FULL_MATCH(TRIM(review_score), '[+-]?[0-9]+')
        THEN TRY_CAST(review_score AS INTEGER) END AS review_score,
    review_comment_title, review_comment_message,
    TRY_CAST(review_creation_date AS TIMESTAMP) AS review_creation_date,
    TRY_CAST(review_answer_timestamp AS TIMESTAMP) AS review_answer_timestamp,
    review_id AS review_id_raw, order_id AS order_id_raw, review_score AS review_score_raw,
    review_comment_title AS review_comment_title_raw, review_comment_message AS review_comment_message_raw,
    review_creation_date AS review_creation_date_raw, review_answer_timestamp AS review_answer_timestamp_raw
FROM raw_reviews;

CREATE OR REPLACE TABLE stg_category_translation AS
SELECT DISTINCT
    NULLIF(TRIM(product_category_name), '') AS product_category_name,
    NULLIF(TRIM(product_category_name_english), '') AS product_category_name_english,
    product_category_name AS product_category_name_raw,
    product_category_name_english AS product_category_name_english_raw
FROM raw_category_translation;
