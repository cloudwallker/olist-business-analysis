-- 业务问题：提供两事实表共享的日期和州维度、明细专用的品类维度。
-- 输出：每日、每州、每品类各一行。日期覆盖全源购买日和配置窗口，保证月份空档可见。
-- 过滤：无业务状态过滤。限制：日期和州关系单向；品类不应筛选订单级经营/履约卡片。
CREATE OR REPLACE TABLE dim_date AS
WITH bounds AS (
    SELECT LEAST(MIN(purchase_date), (SELECT analysis_start FROM analysis_config)) AS first_date,
        GREATEST(MAX(purchase_date), (SELECT analysis_end FROM analysis_config)) AS last_date
    FROM fact_orders
)
SELECT CAST(d AS DATE) AS date,
    CAST(DATE_TRUNC('month', d) AS DATE) AS month_start,
    YEAR(d) AS year, QUARTER(d) AS quarter, MONTH(d) AS month
FROM bounds, LATERAL GENERATE_SERIES(first_date, last_date, INTERVAL '1 day') AS dates(d);

CREATE OR REPLACE TABLE dim_customer_state AS
SELECT DISTINCT customer_state FROM fact_orders
UNION SELECT DISTINCT customer_state FROM fact_order_items
UNION SELECT 'UNKNOWN';

CREATE OR REPLACE TABLE dim_category AS
SELECT DISTINCT category FROM fact_order_items
UNION SELECT 'UNKNOWN';
