-- 问题：每位客户的首次观测已交付购买、等时订单与下一笔严格更晚购买间隔是什么？
-- 输入：订单粒度。筛选：全源最终delivered、有效购买/customer_unique_id、购买不晚于冻结observation_end。
-- 输出：每customer_unique_id一行；不按报告开始日期截断客户历史。
-- 限制：仅数据中的首次观测，非真实首次；客户级输出只作本地校验，不公开标识。不同customer_id仍按unique_id去重。
-- 先合并等时购买事件再LEAD，避免等时订单遮挡后续；第30天计入，第30天+1秒不计。
WITH observed AS (
    SELECT f.* FROM fact_orders f CROSS JOIN analysis_config c
    WHERE f.order_status = 'delivered' AND f.purchase_timestamp IS NOT NULL
        AND f.purchase_timestamp <= c.observation_end AND f.customer_unique_id IS NOT NULL
), events AS (
    SELECT customer_unique_id, purchase_timestamp, MIN(order_id) AS representative_order_id,
        COUNT(*) AS event_orders
    FROM observed GROUP BY customer_unique_id, purchase_timestamp
), sequences AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY customer_unique_id ORDER BY purchase_timestamp) AS event_rank,
        LEAD(purchase_timestamp) OVER (PARTITION BY customer_unique_id ORDER BY purchase_timestamp) AS next_purchase_timestamp,
        LEAD(representative_order_id) OVER (PARTITION BY customer_unique_id ORDER BY purchase_timestamp) AS next_order_id,
        SUM(event_orders) OVER (PARTITION BY customer_unique_id) AS delivered_orders_observed
    FROM events
)
SELECT customer_unique_id, representative_order_id AS first_order_id,
    purchase_timestamp AS first_purchase_timestamp,
    CAST(DATE_TRUNC('month', purchase_timestamp) AS DATE) AS cohort_month,
    delivered_orders_observed, event_orders - 1 AS simultaneous_additional_orders,
    next_order_id, next_purchase_timestamp,
    EPOCH(next_purchase_timestamp - purchase_timestamp) / 86400.0 AS days_to_next_purchase,
    purchase_timestamp + INTERVAL '30 days' <= (SELECT observation_end FROM analysis_config) AS has_30_day_observation,
    COALESCE(next_purchase_timestamp > purchase_timestamp
        AND next_purchase_timestamp <= purchase_timestamp + INTERVAL '30 days', FALSE) AS repeat_within_30_days
FROM sequences WHERE event_rank = 1 ORDER BY first_purchase_timestamp, customer_unique_id;
