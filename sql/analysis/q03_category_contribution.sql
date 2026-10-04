-- 问题：哪些品类构成成交额、贡献月度变化？
-- 输入：商品明细粒度。筛选：配置购买日窗口、最终delivered。
-- 输出：全窗口与每月份×Top10品类/OTHER；Top10按窗口金额固定，OTHER在组内重新去重订单。
-- 限制：品类金额可加；containing_category_orders是含该组品类的去重订单数，跨品类不可相加。
-- 未翻译品类保留原名；缺原品类UNKNOWN。金额质量先验收，变化贡献不代表因果。
WITH items AS (
    SELECT f.* FROM fact_order_items f CROSS JOIN analysis_config c
    WHERE f.purchase_date BETWEEN c.analysis_start AND c.analysis_end AND f.order_status = 'delivered'
), ranked AS (
    SELECT category, SUM(price) AS window_merchandise_value,
        ROW_NUMBER() OVER (ORDER BY SUM(price) DESC, category) AS category_rank
    FROM items GROUP BY category
), mapped AS (
    SELECT i.*, CASE WHEN r.category_rank <= 10 THEN i.category ELSE 'OTHER' END AS displayed_category,
        CASE WHEN r.category_rank <= 10 THEN r.category_rank ELSE 11 END AS displayed_rank
    FROM items i JOIN ranked r USING (category)
), categories AS (
    SELECT DISTINCT displayed_category AS category, displayed_rank AS category_rank FROM mapped
), months AS (
    SELECT CAST(m AS DATE) AS purchase_month FROM analysis_config c,
        LATERAL GENERATE_SERIES(DATE_TRUNC('month', c.analysis_start),
            DATE_TRUNC('month', c.analysis_end), INTERVAL '1 month') AS dates(m)
), monthly AS (
    SELECT m.purchase_month, c.category, c.category_rank,
        COALESCE(SUM(i.price), 0) AS merchandise_value,
        COUNT(DISTINCT i.order_id) AS containing_category_orders
    FROM months m CROSS JOIN categories c
    LEFT JOIN mapped i ON i.purchase_month = m.purchase_month AND i.displayed_category = c.category
    GROUP BY m.purchase_month, c.category, c.category_rank
), previous AS (
    SELECT *, LAG(merchandise_value) OVER (PARTITION BY category ORDER BY purchase_month) AS previous_merchandise_value
    FROM monthly
), changes AS (
    SELECT *, merchandise_value - previous_merchandise_value AS merchandise_change FROM previous
), window_totals AS (
    SELECT displayed_category AS category, displayed_rank AS category_rank,
        SUM(price) AS merchandise_value, COUNT(DISTINCT order_id) AS containing_category_orders
    FROM mapped GROUP BY displayed_category, displayed_rank
)
SELECT 'WINDOW' AS period, NULL::DATE AS purchase_month, category, category_rank,
    merchandise_value, containing_category_orders,
    merchandise_value / NULLIF(SUM(merchandise_value) OVER (), 0) AS merchandise_share,
    NULL::DECIMAL(38,2) AS previous_merchandise_value,
    NULL::DECIMAL(38,2) AS merchandise_change, NULL::DOUBLE AS change_contribution_share
FROM window_totals
UNION ALL
SELECT 'MONTH', purchase_month, category, category_rank, merchandise_value, containing_category_orders,
    merchandise_value / NULLIF(SUM(merchandise_value) OVER (PARTITION BY purchase_month), 0),
    previous_merchandise_value, merchandise_change,
    merchandise_change / NULLIF(SUM(merchandise_change) OVER (PARTITION BY purchase_month), 0)
FROM changes
ORDER BY period DESC, purchase_month NULLS FIRST, category_rank, category;
