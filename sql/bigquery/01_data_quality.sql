-- Data-quality controls for the cloud analytical layer.
-- Non-positive quantities/sales are reported as information because the
-- source contains returns and reversals; they are not silently deleted.

CREATE OR REPLACE TABLE `fmcg_analytics.mart_data_quality` AS
WITH transaction_checks AS (
  SELECT
    COUNT(*) AS row_count,
    COUNT(DISTINCT household_key) AS household_count,
    COUNTIF(household_key IS NULL OR basket_id IS NULL OR product_id IS NULL) AS missing_key_rows,
    COUNTIF(quantity <= 0) AS nonpositive_quantity_rows,
    COUNTIF(sales_value <= 0) AS nonpositive_sales_rows,
    COUNT(*) - COUNT(DISTINCT TO_JSON_STRING(STRUCT(
      household_key, basket_id, day, product_id, quantity, sales_value,
      store_id, retail_disc, trans_time, week_no, coupon_disc,
      coupon_match_disc
    ))) AS exact_duplicate_rows
  FROM `fmcg_analytics.transactions`
),
product_checks AS (
  SELECT COUNT(*) AS orphan_transaction_rows
  FROM `fmcg_analytics.transactions` AS t
  LEFT JOIN `fmcg_analytics.products` AS p USING (product_id)
  WHERE p.product_id IS NULL
),
customer_checks AS (
  SELECT
    COUNT(*) AS row_count,
    COUNT(DISTINCT household_key) AS unique_households,
    COUNTIF(kmeans_segment IS NULL OR rfm_segment IS NULL) AS missing_segment_rows
  FROM `fmcg_analytics.customer_360_kmeans`
),
campaign_checks AS (
  SELECT
    COUNT(*) AS exposure_rows,
    COUNT(DISTINCT campaign) AS campaign_count,
    COUNT(*) - COUNT(DISTINCT CONCAT(CAST(campaign AS STRING), '|', CAST(household_key AS STRING))) AS duplicate_exposures
  FROM `fmcg_analytics.campaign_table`
),
panel_checks AS (
  SELECT
    COUNT(*) AS panel_rows,
    COUNT(DISTINCT event_id) AS event_count,
    COUNTIF(week_count <> 9) AS incomplete_events
  FROM (
    SELECT event_id, COUNT(*) AS week_count
    FROM `fmcg_analytics.matched_promotion_event_panel`
    GROUP BY event_id
  )
),
panel_totals AS (
  SELECT COUNT(*) AS panel_rows
  FROM `fmcg_analytics.matched_promotion_event_panel`
),
checks AS (
  SELECT 'transaction_row_count' AS check_name,
         CAST(t.row_count AS STRING) AS observed_value,
         '2595732' AS expected_rule,
         IF(t.row_count = 2595732, 'PASS', 'REVIEW') AS status
  FROM transaction_checks AS t
  UNION ALL
  SELECT 'unique_households', CAST(t.household_count AS STRING), '2500',
         IF(t.household_count = 2500, 'PASS', 'REVIEW')
  FROM transaction_checks AS t
  UNION ALL
  SELECT 'missing_transaction_keys', CAST(t.missing_key_rows AS STRING), '0',
         IF(t.missing_key_rows = 0, 'PASS', 'FAIL')
  FROM transaction_checks AS t
  UNION ALL
  SELECT 'exact_duplicate_transaction_rows', CAST(t.exact_duplicate_rows AS STRING), '0',
         IF(t.exact_duplicate_rows = 0, 'PASS', 'FAIL')
  FROM transaction_checks AS t
  UNION ALL
  SELECT 'nonpositive_quantity_rows', CAST(t.nonpositive_quantity_rows AS STRING),
         'informational: source returns/reversals retained', 'INFO'
  FROM transaction_checks AS t
  UNION ALL
  SELECT 'nonpositive_sales_rows', CAST(t.nonpositive_sales_rows AS STRING),
         'informational: source returns/reversals retained', 'INFO'
  FROM transaction_checks AS t
  UNION ALL
  SELECT 'orphan_product_transaction_rows', CAST(p.orphan_transaction_rows AS STRING), '0',
         IF(p.orphan_transaction_rows = 0, 'PASS', 'FAIL')
  FROM product_checks AS p
  UNION ALL
  SELECT 'customer_360_household_grain', CAST(c.row_count AS STRING), '2500 rows',
         IF(c.row_count = 2500 AND c.unique_households = 2500, 'PASS', 'FAIL')
  FROM customer_checks AS c
  UNION ALL
  SELECT 'missing_customer_segments', CAST(c.missing_segment_rows AS STRING), '0',
         IF(c.missing_segment_rows = 0, 'PASS', 'FAIL')
  FROM customer_checks AS c
  UNION ALL
  SELECT 'target_exposure_count', CAST(c.exposure_rows AS STRING), '7208',
         IF(c.exposure_rows = 7208, 'PASS', 'REVIEW')
  FROM campaign_checks AS c
  UNION ALL
  SELECT 'campaign_count', CAST(c.campaign_count AS STRING), '30',
         IF(c.campaign_count = 30, 'PASS', 'REVIEW')
  FROM campaign_checks AS c
  UNION ALL
  SELECT 'duplicate_target_exposures', CAST(c.duplicate_exposures AS STRING), '0',
         IF(c.duplicate_exposures = 0, 'PASS', 'FAIL')
  FROM campaign_checks AS c
  UNION ALL
  SELECT 'matched_panel_rows', CAST(p.panel_rows AS STRING), '3807',
         IF(p.panel_rows = 3807, 'PASS', 'REVIEW')
  FROM panel_totals AS p
  UNION ALL
  SELECT 'matched_event_count', CAST(p.event_count AS STRING), '423',
         IF(p.event_count = 423, 'PASS', 'REVIEW')
  FROM panel_checks AS p
  UNION ALL
  SELECT 'incomplete_nine_week_events', CAST(p.incomplete_events AS STRING), '0',
         IF(p.incomplete_events = 0, 'PASS', 'FAIL')
  FROM panel_checks AS p
)
SELECT *, CURRENT_TIMESTAMP() AS checked_at
FROM checks;

SELECT *
FROM `fmcg_analytics.mart_data_quality`
ORDER BY CASE status WHEN 'FAIL' THEN 1 WHEN 'REVIEW' THEN 2 WHEN 'INFO' THEN 3 ELSE 4 END,
         check_name;
