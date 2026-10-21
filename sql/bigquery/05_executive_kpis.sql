-- One row per KPI makes reconciliation and downstream BI consumption simple.

CREATE OR REPLACE TABLE `fmcg_analytics.mart_executive_kpis` AS
WITH store AS (
  SELECT SUM(sales_value) AS sales, COUNT(DISTINCT household_key) AS households
  FROM `fmcg_analytics.transactions`
),
beverage AS (
  SELECT SUM(sales_value) AS sales
  FROM `fmcg_analytics.beverage_transactions`
),
coupon AS (
  SELECT
    SAFE_DIVIDE(SUM(redeeming_households), SUM(targeted_households)) AS penetration
  FROM `fmcg_analytics.mart_coupon_campaign_performance`
),
high_value AS (
  SELECT household_share, revenue_share
  FROM `fmcg_analytics.mart_customer_segment_performance`
  WHERE segment_dimension = 'kmeans_segment'
    AND segment_name = 'High-Value Frequent'
),
promotion AS (
  SELECT * FROM `fmcg_analytics.mart_promotion_summary`
)
SELECT 'total_store_sales' AS metric, s.sales AS value, 'USD' AS unit,
       'observed_behavior' AS evidence_type FROM store AS s
UNION ALL
SELECT 'beverage_sales', b.sales, 'USD', 'observed_behavior' FROM beverage AS b
UNION ALL
SELECT 'beverage_sales_share', SAFE_DIVIDE(b.sales, s.sales), 'share', 'observed_behavior'
FROM beverage AS b CROSS JOIN store AS s
UNION ALL
SELECT 'household_count', CAST(s.households AS FLOAT64), 'count', 'observed_behavior' FROM store AS s
UNION ALL
SELECT 'targeted_coupon_redemption_penetration', c.penetration, 'share', 'observed_behavior' FROM coupon AS c
UNION ALL
SELECT 'high_value_frequent_household_share', h.household_share, 'share', 'model_based_assignment' FROM high_value AS h
UNION ALL
SELECT 'high_value_frequent_revenue_share', h.revenue_share, 'share', 'model_based_assignment' FROM high_value AS h
UNION ALL
SELECT 'matched_promotion_events', CAST(p.matched_events AS FLOAT64), 'count', 'quasi_experimental_estimate' FROM promotion AS p
UNION ALL
SELECT 'incremental_units_per_event', p.incremental_units_per_event, 'units', 'quasi_experimental_estimate' FROM promotion AS p
UNION ALL
SELECT 'incremental_revenue_per_event', p.incremental_revenue_per_event, 'USD', 'quasi_experimental_estimate' FROM promotion AS p;

SELECT *
FROM `fmcg_analytics.mart_executive_kpis`
ORDER BY evidence_type, metric;
