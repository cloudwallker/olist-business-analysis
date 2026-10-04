-- 问题：月度商品成交额、订单数、客单价和取消状态占比是多少？
-- 输入：fact_orders一订单一行。筛选：配置购买日窗口；商品指标仅最终delivered。
-- 输出：每自然月一行，保留空月份。限制：快照状态；不含运费，不代表收入或退款率；金额质量必须先验收。
WITH months AS (
    SELECT CAST(m AS DATE) AS purchase_month
    FROM analysis_config c,
        LATERAL GENERATE_SERIES(DATE_TRUNC('month', c.analysis_start),
            DATE_TRUNC('month', c.analysis_end), INTERVAL '1 month') AS dates(m)
), orders AS (
    SELECT f.* FROM fact_orders f CROSS JOIN analysis_config c
    WHERE f.purchase_date BETWEEN c.analysis_start AND c.analysis_end
), monthly AS (
    SELECT m.purchase_month, COUNT(o.order_id) AS all_orders,
        COUNT(o.order_id) FILTER (WHERE o.order_status = 'delivered') AS delivered_orders,
        COUNT(o.order_id) FILTER (WHERE o.order_status = 'canceled') AS canceled_orders,
        COUNT(o.merchandise_value) FILTER (WHERE o.order_status = 'delivered') AS valid_merchandise_orders,
        CASE WHEN COUNT(o.order_id) FILTER (WHERE o.order_status = 'delivered')
                = COUNT(o.merchandise_value) FILTER (WHERE o.order_status = 'delivered')
            THEN COALESCE(SUM(o.merchandise_value) FILTER (WHERE o.order_status = 'delivered'), 0)
            END AS merchandise_value
    FROM months m LEFT JOIN orders o USING (purchase_month) GROUP BY m.purchase_month
)
SELECT *, merchandise_value / NULLIF(delivered_orders, 0) AS average_order_value,
    canceled_orders::DOUBLE / NULLIF(all_orders, 0) AS canceled_order_share,
    (SELECT analysis_start FROM analysis_config) <= purchase_month
        AND (SELECT analysis_end FROM analysis_config) >= LAST_DAY(purchase_month) AS complete_calendar_month
FROM monthly ORDER BY purchase_month;
