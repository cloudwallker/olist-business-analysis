-- 问题：送达时长的中位数、P90及覆盖是多少？
-- 输入：一订单一行。筛选：配置购买日窗口、最终delivered；时长需购买/实际送达完整且时序有效。
-- 输出：WINDOW、MONTH、STATE三级各一行。限制：不要求预计日期，不用缺物流订单代替零天；仅描述分布。
WITH orders AS (
    SELECT f.* FROM fact_orders f CROSS JOIN analysis_config c
    WHERE f.purchase_date BETWEEN c.analysis_start AND c.analysis_end AND f.order_status = 'delivered'
), groups AS (
    SELECT 'WINDOW' AS scope, NULL::DATE AS purchase_month, NULL::VARCHAR AS customer_state
    UNION ALL
    SELECT 'MONTH', CAST(m AS DATE), NULL::VARCHAR FROM analysis_config c,
        LATERAL GENERATE_SERIES(DATE_TRUNC('month', c.analysis_start),
            DATE_TRUNC('month', c.analysis_end), INTERVAL '1 month') AS dates(m)
    UNION ALL SELECT 'STATE', NULL::DATE, customer_state FROM dim_customer_state
)
SELECT g.scope, g.purchase_month, g.customer_state, COUNT(o.order_id) AS delivered_orders,
    COUNT(o.delivery_days) AS duration_eligible_orders,
    COUNT(o.delivery_days)::DOUBLE / NULLIF(COUNT(o.order_id), 0) AS duration_coverage,
    QUANTILE_CONT(o.delivery_days, 0.5) AS median_delivery_days,
    QUANTILE_CONT(o.delivery_days, 0.9) AS p90_delivery_days,
    MIN(o.delivery_days) AS min_delivery_days, MAX(o.delivery_days) AS max_delivery_days
FROM groups g LEFT JOIN orders o ON g.scope = 'WINDOW'
    OR (g.scope = 'MONTH' AND g.purchase_month = o.purchase_month)
    OR (g.scope = 'STATE' AND g.customer_state = o.customer_state)
GROUP BY g.scope, g.purchase_month, g.customer_state
ORDER BY g.scope DESC, g.purchase_month, g.customer_state;
