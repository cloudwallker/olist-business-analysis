-- One row per order. Execute against the approved warehouse or anonymous export.
-- state_SP; purchase-date window. Currency is unverified source units.
WITH selected AS (
  SELECT * FROM fact_orders
  WHERE purchase_date BETWEEN DATE '2017-02-01' AND DATE '2018-07-31' AND customer_state = 'SP'
), counts AS (
  SELECT
    COALESCE(SUM(merchandise_value) FILTER (WHERE order_status='delivered'),0) AS gmv,
    COUNT(*) FILTER (WHERE order_status='delivered') AS delivered_orders,
    COUNT(*) AS all_orders,
    COUNT(*) FILTER (WHERE order_status='canceled') AS canceled_orders,
    COUNT(*) FILTER (WHERE order_status='delivered' AND delivery_eligible) AS delivery_orders,
    COUNT(*) FILTER (WHERE order_status='delivered' AND delivery_eligible AND is_late) AS late_orders,
    COUNT(*) FILTER (WHERE order_status='delivered' AND review_eligible) AS review_orders,
    COUNT(*) FILTER (WHERE order_status='delivered' AND review_eligible AND review_score IN (1,2)) AS low_score_orders,
    COUNT(*) FILTER (WHERE order_status='delivered' AND delivery_eligible AND review_eligible) AS joint_orders,
    COUNT(delivery_days) FILTER (WHERE order_status='delivered') AS duration_orders,
    QUANTILE_CONT(delivery_days,0.5) FILTER (WHERE order_status='delivered') AS p50_days,
    QUANTILE_CONT(delivery_days,0.9) FILTER (WHERE order_status='delivered') AS p90_days
  FROM selected
)
SELECT *,
  gmv / NULLIF(delivered_orders,0) AS aov,
  canceled_orders::DOUBLE / NULLIF(all_orders,0) AS cancel_rate,
  late_orders::DOUBLE / NULLIF(delivery_orders,0) AS late_rate,
  low_score_orders::DOUBLE / NULLIF(review_orders,0) AS low_score_rate,
  delivery_orders::DOUBLE / NULLIF(delivered_orders,0) AS delivery_coverage,
  review_orders::DOUBLE / NULLIF(delivered_orders,0) AS review_coverage,
  joint_orders::DOUBLE / NULLIF(delivered_orders,0) AS joint_coverage,
  duration_orders::DOUBLE / NULLIF(delivered_orders,0) AS duration_coverage
FROM counts;
