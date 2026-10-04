-- 问题：首次观测客户中，具有完整30天观察期者的30天复购比例及观察覆盖是多少？
-- 输入：订单粒度。筛选：全源delivered购买先识别首次；购买<=observation_end，展示首次购买日在配置报告窗口的cohort。
-- 输出：每cohort自然月一行，包括空月；成熟、未成熟、等时客户计数可见。
-- 限制：第30天计入，第31天不计；等时不同订单不算复购；不足观察期不进分母；部分成熟月不能冒充完整cohort。
WITH observed AS (
    SELECT f.order_id, f.customer_unique_id, f.purchase_timestamp
    FROM fact_orders f CROSS JOIN analysis_config c
    WHERE f.order_status = 'delivered' AND f.purchase_timestamp IS NOT NULL
        AND f.purchase_timestamp <= c.observation_end AND f.customer_unique_id IS NOT NULL
), events AS (
    SELECT customer_unique_id, purchase_timestamp, COUNT(*) AS event_orders
    FROM observed GROUP BY customer_unique_id, purchase_timestamp
), sequences AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY customer_unique_id ORDER BY purchase_timestamp) AS event_rank,
        LEAD(purchase_timestamp) OVER (PARTITION BY customer_unique_id ORDER BY purchase_timestamp) AS next_purchase_timestamp
    FROM events
), customers AS (
    SELECT customer_unique_id, CAST(DATE_TRUNC('month', purchase_timestamp) AS DATE) AS cohort_month,
        event_orders - 1 AS simultaneous_additional_orders,
        purchase_timestamp + INTERVAL '30 days' <= c.observation_end AS eligible,
        COALESCE(next_purchase_timestamp > purchase_timestamp
            AND next_purchase_timestamp <= purchase_timestamp + INTERVAL '30 days', FALSE) AS repeated
    FROM sequences CROSS JOIN analysis_config c
    WHERE event_rank = 1 AND CAST(purchase_timestamp AS DATE) BETWEEN c.analysis_start AND c.analysis_end
), months AS (
    SELECT CAST(m AS DATE) AS cohort_month FROM analysis_config c,
        LATERAL GENERATE_SERIES(DATE_TRUNC('month', c.analysis_start),
            DATE_TRUNC('month', c.analysis_end), INTERVAL '1 month') AS dates(m)
), counts AS (
    SELECT m.cohort_month, COUNT(u.customer_unique_id) AS total_customers,
        COUNT(u.customer_unique_id) FILTER (WHERE u.eligible) AS eligible_customers,
        COUNT(u.customer_unique_id) FILTER (WHERE NOT u.eligible) AS immature_customers,
        COUNT(u.customer_unique_id) FILTER (WHERE u.eligible AND u.repeated) AS repeat_customers_30d,
        COUNT(u.customer_unique_id) FILTER (WHERE u.simultaneous_additional_orders > 0) AS customers_with_simultaneous_orders,
        COALESCE(SUM(u.simultaneous_additional_orders), 0) AS simultaneous_additional_orders
    FROM months m LEFT JOIN customers u USING (cohort_month) GROUP BY m.cohort_month
)
SELECT *, repeat_customers_30d::DOUBLE / NULLIF(eligible_customers, 0) AS repeat_share_30d,
    eligible_customers::DOUBLE / NULLIF(total_customers, 0) AS observation_coverage,
    CASE WHEN total_customers = 0 THEN 'EMPTY'
         WHEN eligible_customers = total_customers THEN 'ALL_OBSERVED_CUSTOMERS_MATURE'
         WHEN eligible_customers = 0 THEN 'IMMATURE' ELSE 'PARTIALLY_MATURE' END AS maturity_status,
    cohort_month + INTERVAL '1 month' + INTERVAL '30 days' - INTERVAL '1 microsecond'
        <= (SELECT observation_end FROM analysis_config) AS fully_observed_calendar_cohort,
    (SELECT observation_end FROM analysis_config) AS observation_end
FROM counts ORDER BY cohort_month;
