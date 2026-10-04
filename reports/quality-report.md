# 数据质量与复现证据

必要检查 47/47 通过，阻断失败 0；非零警告 9 项。

本报告只接受成功运行。检查包含业务键/关联粒度、金额有效性、缺明细、事实金额、月度与 Top 10 加其他对账、量价分解残差。下表质量计数覆盖**全源模型**；一页结论则使用配置购买窗口，二者分母不同。

| 非零警告 | 值 | 解释 |
|---|---:|---|
| products.missing_category | 610 | 金额保留，缺原品类归 UNKNOWN。 |
| products.untranslated_category | 13 | 保留原品类名称，不误归缺失品类。 |
| delivery.missing_or_invalid | 8 | 订单保留经营金额，退出对应物流分母。 |
| delivered.missing_payment | 1 | 支付不替代商品成交额，不自动删除订单。 |
| payment.reconciliation_difference | 576 | 支付与商品加运费有差异，保留原值。 |
| payment.reconciliation_difference_gt_cent | 303 | 绝对支付核对差异超过 0.01 原始单位。 |
| reviews.multiple_orders | 547 | 按回答时间、创建时间、review_id 选择一条；评价不参与金额聚合。 |
| reviews.missing_or_invalid | 646 | 退出评分分母；不算低评分或高评分。 |
| reviews.before_delivery | 4653 | 有效交集中的回答早于送达，进行 Q08 时序敏感性对照。 |

所有必需检查及对账的原始统计：

| 检查 | 值 | 级别 | 结果 |
|---|---:|---|---|
| orders.key_conflicts | 0 | error | 通过 |
| orders.missing_key | 0 | error | 通过 |
| orders.exact_duplicate_rows | 0 | warning | 通过 |
| items.key_conflicts | 0 | error | 通过 |
| items.missing_key | 0 | error | 通过 |
| items.exact_duplicate_rows | 0 | warning | 通过 |
| payments.key_conflicts | 0 | error | 通过 |
| payments.missing_key | 0 | error | 通过 |
| payments.exact_duplicate_rows | 0 | warning | 通过 |
| customers.key_conflicts | 0 | error | 通过 |
| customers.missing_key | 0 | error | 通过 |
| customers.exact_duplicate_rows | 0 | warning | 通过 |
| products.key_conflicts | 0 | error | 通过 |
| products.missing_key | 0 | error | 通过 |
| products.exact_duplicate_rows | 0 | warning | 通过 |
| reviews.key_conflicts | 0 | error | 通过 |
| reviews.missing_key | 0 | error | 通过 |
| reviews.exact_duplicate_rows | 0 | warning | 通过 |
| category_translation.key_conflicts | 0 | error | 通过 |
| category_translation.missing_key | 0 | error | 通过 |
| category_translation.exact_duplicate_rows | 0 | warning | 通过 |
| items.price.invalid_amount | 0 | error | 通过 |
| items.freight_value.invalid_amount | 0 | error | 通过 |
| payments.payment_value.invalid_amount | 0 | error | 通过 |
| items.order_item_id.invalid_key | 0 | error | 通过 |
| payments.payment_sequential.invalid_key | 0 | error | 通过 |
| orders.invalid_purchase_timestamp | 0 | error | 通过 |
| customers.missing_unique_identifier | 0 | error | 通过 |
| orders.invalid_status | 0 | error | 通过 |
| reviews.invalid_score | 0 | warning | 通过 |
| reviews.ambiguous_selection | 0 | error | 通过 |
| orders.customer_id.unmatched | 0 | error | 通过 |
| items.order_id.unmatched | 0 | error | 通过 |
| items.product_id.unmatched | 0 | error | 通过 |
| payments.order_id.unmatched | 0 | error | 通过 |
| reviews.order_id.unmatched | 0 | error | 通过 |
| products.missing_category | 610 | warning | 警告 |
| products.untranslated_category | 13 | warning | 警告 |
| orders.order_approved_at.invalid_timestamp | 0 | warning | 通过 |
| orders.order_delivered_carrier_date.invalid_timestamp | 0 | warning | 通过 |
| orders.order_delivered_customer_date.invalid_timestamp | 0 | warning | 通过 |
| orders.order_estimated_delivery_date.invalid_timestamp | 0 | warning | 通过 |
| reviews.review_creation_date.invalid_timestamp | 0 | warning | 通过 |
| reviews.review_answer_timestamp.invalid_timestamp | 0 | warning | 通过 |
| items.shipping_limit_date.invalid_timestamp | 0 | warning | 通过 |
| fact_orders.row_count | 0 | error | 通过 |
| fact_orders.key_unique | 0 | error | 通过 |
| fact_order_items.row_count | 0 | error | 通过 |
| fact_order_items.key_unique | 0 | error | 通过 |
| delivered.merchandise_missing | 0 | error | 通过 |
| merchandise.items_to_orders | 0.00 | error | 通过 |
| merchandise.items_to_enriched_items | 0.00 | error | 通过 |
| merchandise.delivered_grain | 0.00 | error | 通过 |
| delivery.invalid_flag | 0 | error | 通过 |
| delivery.missing_or_invalid | 8 | warning | 警告 |
| delivery.invalid_sequence | 0 | warning | 通过 |
| delivered.missing_payment | 1 | warning | 警告 |
| payment.reconciliation_difference | 576 | warning | 警告 |
| payment.reconciliation_difference_gt_cent | 303 | warning | 警告 |
| reviews.multiple_orders | 547 | warning | 警告 |
| reviews.missing_or_invalid | 646 | warning | 警告 |
| reviews.before_delivery | 4653 | warning | 警告 |
| analysis.q01.result_count | 0 | error | 通过 |
| analysis.q02.result_count | 0 | error | 通过 |
| analysis.q03.result_count | 0 | error | 通过 |
| analysis.q01.window_merchandise | 0.00 | error | 通过 |
| analysis.q03.window_merchandise | 0.00 | error | 通过 |
| analysis.q01.month_merchandise | 0 | error | 通过 |
| analysis.q01.month_unique | 0 | error | 通过 |
| analysis.q03.month_merchandise | 0 | error | 通过 |
| analysis.q01.month_boundary_flags | 0 | error | 通过 |
| analysis.q02.decomposition_residual | 0 | error | 通过 |

来源文件与快照证据（只展示文件名与摘要，不含个人本地路径或记录标识）：

| CSV | 行数 | SHA-256 |
|---|---:|---|
| olist_orders_dataset.csv | 99,441 | `8df58ef3d2d7e9944010f7beecd9b75367f5588ec6e3c91cec19ae3345ef9ecf` |
| olist_order_items_dataset.csv | 112,650 | `0bc4d068c4fe38cbb01bd90e8746e3c613fe7b4baef75fab7b0e329701c3e279` |
| olist_order_payments_dataset.csv | 103,886 | `4f713964f2815dbbaa40b9488268c55aac3627bfce5aa96cf58d1f3616de3cc0` |
| olist_customers_dataset.csv | 99,441 | `983a422239e1712ded753b3bf9ecf47dc73f144d306029dcfa99e70a226883d2` |
| olist_products_dataset.csv | 32,951 | `3e6569628a17fbc75fd206ee357b59e20364b9afa90f5b6cd5b4d624c58aa9cc` |
| olist_order_reviews_dataset.csv | 99,224 | `012b61c7593e34f51fa614efdf802b9c7056ce6aae5307ddb93236e7cfc797d7` |
| product_category_name_translation.csv | 71 | `a81f0d1f27b27e7293f761bc79e3ce8f348ee39c4b3ed3e49bde38f478586278` |

Python 3.9.25；DuckDB 1.4.5；本次流水线实测 19.261758 秒。耗时包含导入、质量检查与导出，受电脑环境影响。

购买窗口 2017-02-01—2018-07-31；观察截止 2018-07-31 23:59:59；冻结窗口依据逐日源覆盖审核，不能被更晚物流/评价或稀疏购买尾段延长。

快照指纹 `7a62574c036cfc583f5366dd39922523f49ce4a7172d617ba05e0017b87064f1`。

来源：[Olist 数据卡](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)；许可：[CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)。金额为原始数据单位（币种未核验）；本项目进行了清洗、聚合和统计分析。
