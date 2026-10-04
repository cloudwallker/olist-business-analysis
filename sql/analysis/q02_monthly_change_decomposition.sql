-- 问题：月度金额变化由订单数与客单价如何顺序分解？
-- 输入：订单粒度。筛选：配置购买日窗口、最终delivered；空月份连续保留。
-- 输出：每自然月一行。限制：订单数贡献先算，客单价后算；算术归因依赖顺序，不是因果。
-- 任何一月客单价无定义时，相关分解返回NULL；上月金额0时增长率NULL。
WITH months AS (
    SELECT CAST(m AS DATE) AS purchase_month
    FROM analysis_config c,
        LATERAL GENERATE_SERIES(DATE_TRUNC('month', c.analysis_start),
            DATE_TRUNC('month', c.analysis_end), INTERVAL '1 month') AS dates(m)
), orders AS (
    SELECT f.* FROM fact_orders f CROSS JOIN analysis_config c
    WHERE f.purchase_date BETWEEN c.analysis_start AND c.analysis_end AND f.order_status = 'delivered'
), monthly AS (
    SELECT m.purchase_month, COUNT(o.order_id) AS delivered_orders,
        CASE WHEN COUNT(o.order_id) = COUNT(o.merchandise_value)
            THEN COALESCE(SUM(o.merchandise_value), 0) END AS merchandise_value
    FROM months m LEFT JOIN orders o USING (purchase_month) GROUP BY m.purchase_month
), averages AS (
    SELECT *, merchandise_value / NULLIF(delivered_orders, 0) AS average_order_value FROM monthly
), previous AS (
    SELECT *, LAG(merchandise_value) OVER (ORDER BY purchase_month) AS previous_merchandise_value,
        LAG(delivered_orders) OVER (ORDER BY purchase_month) AS previous_delivered_orders,
        LAG(average_order_value) OVER (ORDER BY purchase_month) AS previous_average_order_value
    FROM averages
), contributions AS (
    SELECT *, merchandise_value - previous_merchandise_value AS merchandise_change,
        (merchandise_value - previous_merchandise_value) / NULLIF(previous_merchandise_value, 0) AS merchandise_change_rate,
        (delivered_orders - previous_delivered_orders) * previous_average_order_value AS order_count_contribution,
        delivered_orders * (average_order_value - previous_average_order_value) AS average_order_value_contribution
    FROM previous
)
SELECT *, merchandise_change - order_count_contribution - average_order_value_contribution AS decomposition_residual
FROM contributions ORDER BY purchase_month;
