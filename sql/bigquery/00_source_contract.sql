-- BigQuery / GoogleSQL
-- Run after the nine local source files listed in sql/README.md have been
-- uploaded to the fmcg_analytics dataset.

CREATE OR REPLACE TABLE `fmcg_analytics.metadata_source_contract` AS
SELECT 'transactions' AS table_name, 'transaction line' AS grain,
       'observed_behavior' AS evidence_type, 2595732 AS expected_rows,
       'data/processed/transactions.parquet' AS local_source
UNION ALL
SELECT 'products', 'product', 'reference_dimension', 92353,
       'data/processed/products.parquet'
UNION ALL
SELECT 'beverage_transactions', 'beverage transaction line',
       'observed_behavior', 235979,
       'data/processed/beverage_transactions.parquet'
UNION ALL
SELECT 'campaign_table', 'targeted household-campaign exposure',
       'observed_targeting', 7208,
       'data/processed/campaign_table.parquet'
UNION ALL
SELECT 'campaign_desc', 'campaign', 'reference_dimension', 30,
       'data/processed/campaign_desc.parquet'
UNION ALL
SELECT 'coupon_redempt', 'coupon redemption transaction',
       'observed_behavior', 2318,
       'data/processed/coupon_redempt.parquet'
UNION ALL
SELECT 'coupon', 'coupon-product-campaign mapping',
       'reference_dimension', 124548,
       'data/processed/coupon.parquet'
UNION ALL
SELECT 'customer_360_kmeans', 'household', 'model_assignment', 2500,
       'data/local_exports/customer_360_kmeans.csv'
UNION ALL
SELECT 'matched_promotion_event_panel', 'matched event-relative week',
       'quasi_experimental_input', 3807,
       'data/processed/matched_promotion_event_panel.parquet';

SELECT *
FROM `fmcg_analytics.metadata_source_contract`
ORDER BY table_name;
