-- 问题：每购买月、每客户州的延迟比例及日期/评分交集覆盖如何变化？
-- 输入：一订单一行。筛选：配置购买日窗口、最终delivered。
-- 输出：完整月份×州；分子分母及覆盖均可重聚合。限制：缺日期不是准时；按日期比较迟到，不把同日午夜当逾期。
WITH months AS (
    SELECT CAST(m AS DATE) AS purchase_month FROM analysis_config c,
        LATERAL GENERATE_SERIES(DATE_TRUNC('month', c.analysis_start),
            DATE_TRUNC('month', c.analysis_end), INTERVAL '1 month') AS dates(m)
), orders AS (
    SELECT f.* FROM fact_orders f CROSS JOIN analysis_config c
    WHERE f.purchase_date BETWEEN c.analysis_start AND c.analysis_end AND f.order_status = 'delivered'
), counts AS (
    SELECT m.purchase_month, s.customer_state, COUNT(o.order_id) AS delivered_orders,
        COUNT(o.order_id) FILTER (WHERE o.delivery_eligible) AS delivery_eligible_orders,
        COUNT(o.order_id) FILTER (WHERE o.is_late) AS late_orders,
        COUNT(o.order_id) FILTER (WHERE o.review_eligible) AS review_eligible_orders,
        COUNT(o.order_id) FILTER (WHERE o.delivery_eligible AND o.review_eligible) AS joint_eligible_orders,
        COUNT(o.order_id) FILTER (WHERE o.delivery_eligible AND o.review_eligible AND o.review_score <= 2) AS joint_low_score_orders
    FROM months m CROSS JOIN dim_customer_state s
    LEFT JOIN orders o ON o.purchase_month = m.purchase_month AND o.customer_state = s.customer_state
    GROUP BY m.purchase_month, s.customer_state
)
SELECT *, delivered_orders - delivery_eligible_orders AS missing_or_invalid_delivery_orders,
    late_orders::DOUBLE / NULLIF(delivery_eligible_orders, 0) AS late_share,
    delivery_eligible_orders::DOUBLE / NULLIF(delivered_orders, 0) AS delivery_coverage,
    review_eligible_orders::DOUBLE / NULLIF(delivered_orders, 0) AS review_coverage,
    joint_eligible_orders::DOUBLE / NULLIF(delivered_orders, 0) AS joint_coverage,
    joint_low_score_orders::DOUBLE / NULLIF(joint_eligible_orders, 0) AS joint_low_score_share
FROM counts ORDER BY purchase_month, customer_state;
