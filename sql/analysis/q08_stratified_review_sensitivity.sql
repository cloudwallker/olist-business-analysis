-- 问题：同月份、同州内准时与延迟的低评分差异是否稳定？剔除提前回答评价后如何变化？
-- 输入：订单粒度。筛选：配置购买日窗口、最终delivered、合格物流和评分交集。
-- 输出：每购买月×州×样本(全部交集/剔除提前回答)；各组分子分母、回答覆盖及阈值标记。
-- 限制：缺回答时间保留并单列覆盖；任一组低于配置阈值仅描述，阈值不代表显著性；不作因果推断。
WITH months AS (
    SELECT CAST(m AS DATE) AS purchase_month FROM analysis_config c,
        LATERAL GENERATE_SERIES(DATE_TRUNC('month', c.analysis_start),
            DATE_TRUNC('month', c.analysis_end), INTERVAL '1 month') AS dates(m)
), orders AS (
    SELECT f.* FROM fact_orders f CROSS JOIN analysis_config c
    WHERE f.purchase_date BETWEEN c.analysis_start AND c.analysis_end AND f.order_status = 'delivered'
        AND f.delivery_eligible AND f.review_eligible
), samples AS (
    SELECT 'ALL_JOINT' AS sample UNION ALL SELECT 'EXCLUDE_EARLY_ANSWERS'
), early AS (
    SELECT purchase_month, customer_state, COUNT(*) FILTER (WHERE review_before_delivery) AS early_orders
    FROM orders GROUP BY purchase_month, customer_state
), counts AS (
    SELECT m.purchase_month, s.customer_state, a.sample,
        COUNT(o.order_id) AS joint_eligible_orders,
        COUNT(o.order_id) FILTER (WHERE NOT o.is_late) AS on_time_orders,
        COUNT(o.order_id) FILTER (WHERE o.is_late) AS late_orders,
        COUNT(o.order_id) FILTER (WHERE NOT o.is_late AND o.review_score <= 2) AS on_time_low_score_orders,
        COUNT(o.order_id) FILTER (WHERE o.is_late AND o.review_score <= 2) AS late_low_score_orders,
        COUNT(o.order_id) FILTER (WHERE o.review_answer_timestamp IS NOT NULL) AS answer_timestamp_orders,
        COUNT(o.order_id) FILTER (WHERE o.review_before_delivery) AS early_answer_orders
    FROM months m CROSS JOIN dim_customer_state s CROSS JOIN samples a
    LEFT JOIN orders o ON o.purchase_month = m.purchase_month AND o.customer_state = s.customer_state
        AND (a.sample = 'ALL_JOINT' OR o.review_before_delivery IS DISTINCT FROM TRUE)
    GROUP BY m.purchase_month, s.customer_state, a.sample
), rates AS (
    SELECT *, on_time_low_score_orders::DOUBLE / NULLIF(on_time_orders, 0) AS on_time_low_score_share,
        late_low_score_orders::DOUBLE / NULLIF(late_orders, 0) AS late_low_score_share,
        answer_timestamp_orders::DOUBLE / NULLIF(joint_eligible_orders, 0) AS answer_timestamp_coverage,
        on_time_orders >= (SELECT min_group_orders FROM analysis_config)
            AND late_orders >= (SELECT min_group_orders FROM analysis_config) AS meets_group_threshold
    FROM counts
)
SELECT r.*, late_low_score_share - on_time_low_score_share AS low_score_share_gap,
    CASE WHEN sample = 'EXCLUDE_EARLY_ANSWERS' THEN COALESCE(e.early_orders, 0) ELSE 0 END AS excluded_early_answer_orders,
    (SELECT min_group_orders FROM analysis_config) AS min_group_orders
FROM rates r LEFT JOIN early e USING (purchase_month, customer_state)
ORDER BY purchase_month, customer_state, sample;
