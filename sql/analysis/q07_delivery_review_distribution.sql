-- 问题：准时与延迟订单的评分分布和低评分比例有何差异？
-- 输入：订单粒度。筛选：配置购买日窗口、最终delivered且同时具备合格配送日期和有效1—5评分。
-- 输出：ON_TIME/LATE两行，提供各评分计数及低评分分子分母。
-- 限制：仅交集样本；最新评价不代表全部体验；观察性关联不能据此推断延迟导致差评。
WITH orders AS (
    SELECT f.* FROM fact_orders f CROSS JOIN analysis_config c
    WHERE f.purchase_date BETWEEN c.analysis_start AND c.analysis_end AND f.order_status = 'delivered'
        AND f.delivery_eligible AND f.review_eligible
), groups AS (
    SELECT 'ON_TIME' AS delivery_group, FALSE AS is_late UNION ALL SELECT 'LATE', TRUE
), counts AS (
    SELECT g.delivery_group, COUNT(o.order_id) AS joint_eligible_orders,
        COUNT(o.order_id) FILTER (WHERE o.review_score <= 2) AS low_score_orders,
        COUNT(o.order_id) FILTER (WHERE o.review_score = 1) AS score_1_orders,
        COUNT(o.order_id) FILTER (WHERE o.review_score = 2) AS score_2_orders,
        COUNT(o.order_id) FILTER (WHERE o.review_score = 3) AS score_3_orders,
        COUNT(o.order_id) FILTER (WHERE o.review_score = 4) AS score_4_orders,
        COUNT(o.order_id) FILTER (WHERE o.review_score = 5) AS score_5_orders,
        COUNT(o.order_id) FILTER (WHERE o.review_answer_timestamp IS NOT NULL) AS answer_timestamp_orders,
        COUNT(o.order_id) FILTER (WHERE o.review_before_delivery) AS early_answer_orders
    FROM groups g LEFT JOIN orders o ON g.is_late = o.is_late GROUP BY g.delivery_group
)
SELECT *, low_score_orders::DOUBLE / NULLIF(joint_eligible_orders, 0) AS low_score_share,
    score_1_orders::DOUBLE / NULLIF(joint_eligible_orders, 0) AS score_1_share,
    score_2_orders::DOUBLE / NULLIF(joint_eligible_orders, 0) AS score_2_share,
    score_3_orders::DOUBLE / NULLIF(joint_eligible_orders, 0) AS score_3_share,
    score_4_orders::DOUBLE / NULLIF(joint_eligible_orders, 0) AS score_4_share,
    score_5_orders::DOUBLE / NULLIF(joint_eligible_orders, 0) AS score_5_share,
    answer_timestamp_orders::DOUBLE / NULLIF(joint_eligible_orders, 0) AS answer_timestamp_coverage
FROM counts ORDER BY delivery_group;
