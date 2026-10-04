-- 业务问题：建立不因一对多关联放大金额的订单与明细事实。
-- 输入：清洗后的7表。输出：每订单一行、每(order_id, order_item_id)一行。
-- 过滤：保留全源状态/日期，缺物流保留经营金额。限制：关键键冲突和无效金额由质量层阻止发布。
CREATE OR REPLACE TABLE fact_orders AS
WITH item_totals AS (
    SELECT order_id, COUNT(*) AS item_count,
        CASE WHEN COUNT(price) = COUNT(*) AND BOOL_AND(price >= 0)
             THEN CAST(SUM(price) AS DECIMAL(18,2)) END AS merchandise_value,
        CASE WHEN COUNT(freight_value) = COUNT(*) AND BOOL_AND(freight_value >= 0)
             THEN CAST(SUM(freight_value) AS DECIMAL(18,2)) END AS freight_value
    FROM stg_items GROUP BY order_id
), payment_totals AS (
    SELECT order_id,
        CASE WHEN COUNT(payment_value) = COUNT(*) AND BOOL_AND(payment_value >= 0)
             THEN CAST(SUM(payment_value) AS DECIMAL(18,2)) END AS payment_value
    FROM stg_payments GROUP BY order_id
), ranked_reviews AS (
    SELECT *, ROW_NUMBER() OVER (
        PARTITION BY order_id ORDER BY review_answer_timestamp DESC NULLS LAST,
            review_creation_date DESC NULLS LAST, review_id ASC NULLS LAST,
            review_score ASC NULLS LAST
    ) AS selected_review_rank
    FROM stg_reviews
    -- 最后一项仅稳定失败候选；前三个排序键全同而评分冲突必须由质量层失败，不能作为已审核选择。
), joined AS (
    SELECT o.order_id, c.customer_unique_id,
        COALESCE(c.customer_state, 'UNKNOWN') AS customer_state,
        o.order_status, o.order_purchase_timestamp AS purchase_timestamp,
        CAST(o.order_purchase_timestamp AS DATE) AS purchase_date,
        CAST(DATE_TRUNC('month', o.order_purchase_timestamp) AS DATE) AS purchase_month,
        COALESCE(i.item_count, 0) AS item_count, i.merchandise_value, i.freight_value, p.payment_value,
        o.order_delivered_customer_date AS delivered_timestamp,
        o.order_estimated_delivery_date AS estimated_delivery_timestamp,
        r.review_score, r.review_answer_timestamp, r.review_creation_date
    FROM stg_orders o
    LEFT JOIN item_totals i USING (order_id)
    LEFT JOIN payment_totals p USING (order_id)
    LEFT JOIN stg_customers c USING (customer_id)
    LEFT JOIN ranked_reviews r ON o.order_id = r.order_id AND r.selected_review_rank = 1
), flags AS (
    SELECT *,
        CASE WHEN order_status = 'delivered' AND purchase_timestamp IS NOT NULL
            AND delivered_timestamp >= purchase_timestamp
            THEN EPOCH(delivered_timestamp - purchase_timestamp) / 86400.0 END AS delivery_days,
        COALESCE(order_status = 'delivered' AND purchase_timestamp IS NOT NULL
            AND delivered_timestamp >= purchase_timestamp
            AND estimated_delivery_timestamp >= purchase_timestamp, FALSE) AS delivery_eligible,
        COALESCE(review_score BETWEEN 1 AND 5, FALSE) AS review_eligible,
        CASE WHEN review_answer_timestamp IS NOT NULL AND delivered_timestamp IS NOT NULL
            THEN review_answer_timestamp < delivered_timestamp END AS review_before_delivery
    FROM joined
)
SELECT *, CASE WHEN delivery_eligible
    THEN CAST(delivered_timestamp AS DATE) > CAST(estimated_delivery_timestamp AS DATE)
    END AS is_late
FROM flags;

CREATE OR REPLACE TABLE fact_order_items AS
SELECT i.order_id, i.order_item_id, i.product_id,
    COALESCE(t.product_category_name_english, p.product_category_name, 'UNKNOWN') AS category,
    COALESCE(c.customer_state, 'UNKNOWN') AS customer_state,
    o.order_status, o.order_purchase_timestamp AS purchase_timestamp,
    CAST(o.order_purchase_timestamp AS DATE) AS purchase_date,
    CAST(DATE_TRUNC('month', o.order_purchase_timestamp) AS DATE) AS purchase_month,
    i.price, i.freight_value
FROM stg_items i
LEFT JOIN stg_orders o USING (order_id)
LEFT JOIN stg_customers c USING (customer_id)
LEFT JOIN stg_products p USING (product_id)
LEFT JOIN stg_category_translation t USING (product_category_name);
