-- 问题：各客户州贡献多少商品成交额，哪些州的履约值得优先调查？
-- 输入：一订单一行。筛选：配置购买日窗口、最终delivered。
-- 输出：每客户州一行，保留规模、覆盖率与问题分子分母。
-- 限制：仅达到配置州订单阈值且有物流样本才按延迟比例/延迟单数排名；不制造综合分数或收入损失。
WITH orders AS (
    SELECT f.* FROM fact_orders f CROSS JOIN analysis_config c
    WHERE f.purchase_date BETWEEN c.analysis_start AND c.analysis_end AND f.order_status = 'delivered'
), state_counts AS (
    SELECT customer_state, COUNT(*) AS delivered_orders,
        CASE WHEN COUNT(*) = COUNT(merchandise_value) THEN SUM(merchandise_value) END AS merchandise_value,
        COUNT(*) FILTER (WHERE delivery_eligible) AS delivery_eligible_orders,
        COUNT(*) FILTER (WHERE is_late) AS late_orders,
        COUNT(*) FILTER (WHERE review_eligible) AS review_eligible_orders,
        COUNT(*) FILTER (WHERE review_eligible AND review_score <= 2) AS low_score_orders,
        COUNT(*) FILTER (WHERE delivery_eligible AND review_eligible) AS joint_eligible_orders,
        COUNT(*) FILTER (WHERE delivery_eligible AND review_eligible AND review_score <= 2) AS joint_low_score_orders
    FROM orders GROUP BY customer_state
), rates AS (
    SELECT *, merchandise_value / NULLIF(SUM(merchandise_value) OVER (), 0) AS merchandise_share,
        ROW_NUMBER() OVER (ORDER BY merchandise_value DESC NULLS LAST, customer_state) AS merchandise_rank,
        delivery_eligible_orders::DOUBLE / NULLIF(delivered_orders, 0) AS delivery_coverage,
        review_eligible_orders::DOUBLE / NULLIF(delivered_orders, 0) AS review_coverage,
        joint_eligible_orders::DOUBLE / NULLIF(delivered_orders, 0) AS joint_coverage,
        late_orders::DOUBLE / NULLIF(delivery_eligible_orders, 0) AS late_share,
        low_score_orders::DOUBLE / NULLIF(review_eligible_orders, 0) AS low_score_share,
        joint_low_score_orders::DOUBLE / NULLIF(joint_eligible_orders, 0) AS joint_low_score_share,
        delivered_orders >= (SELECT min_state_orders FROM analysis_config) AND delivery_eligible_orders > 0 AS meets_state_threshold
    FROM state_counts
), priority AS (
    SELECT customer_state,
        ROW_NUMBER() OVER (ORDER BY late_share DESC, late_orders DESC, delivered_orders DESC, customer_state) AS investigation_rank
    FROM rates WHERE meets_state_threshold
)
SELECT r.*, p.investigation_rank, (SELECT min_state_orders FROM analysis_config) AS min_state_orders
FROM rates r LEFT JOIN priority p USING (customer_state)
ORDER BY investigation_rank NULLS LAST, merchandise_rank;
