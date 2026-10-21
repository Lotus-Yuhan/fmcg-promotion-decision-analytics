-- Customer segmentation: an independent SQL RFM build plus performance of
-- the validated K-Means assignments used on the Power BI customer page.

CREATE OR REPLACE TABLE `fmcg_analytics.mart_customer_rfm_sql` AS
WITH household_value AS (
  SELECT
    household_key,
    MAX(day) AS last_purchase_day,
    COUNT(DISTINCT basket_id) AS frequency_baskets,
    ROUND(SUM(sales_value), 2) AS monetary_value,
    COUNT(DISTINCT product_id) AS unique_products
  FROM `fmcg_analytics.transactions`
  GROUP BY household_key
),
features AS (
  SELECT
    *,
    MAX(last_purchase_day) OVER () - last_purchase_day AS recency_days
  FROM household_value
),
scored AS (
  SELECT
    *,
    NTILE(5) OVER (ORDER BY recency_days DESC) AS r_score,
    NTILE(5) OVER (ORDER BY frequency_baskets ASC) AS f_score,
    NTILE(5) OVER (ORDER BY monetary_value ASC) AS m_score
  FROM features
)
SELECT
  *,
  CONCAT(CAST(r_score AS STRING), CAST(f_score AS STRING), CAST(m_score AS STRING)) AS rfm_score,
  CASE
    WHEN r_score >= 4 AND f_score >= 4 AND m_score >= 4 THEN 'Champions'
    WHEN r_score >= 3 AND f_score >= 4 AND m_score >= 3 THEN 'Loyal'
    WHEN r_score >= 3 AND m_score >= 4 THEN 'Big Spenders'
    WHEN r_score >= 4 AND f_score <= 2 THEN 'New / Low-Frequency'
    WHEN r_score <= 2 AND (f_score >= 4 OR m_score >= 4) THEN 'At-Risk High-Value'
    WHEN r_score <= 2 AND f_score <= 2 THEN 'Hibernating'
    WHEN r_score >= 4 AND f_score BETWEEN 2 AND 3 THEN 'Promising'
    ELSE 'Needs Attention'
  END AS rfm_segment,
  'observed_behavior' AS evidence_type
FROM scored;

CREATE OR REPLACE TABLE `fmcg_analytics.mart_customer_segment_performance` AS
WITH totals AS (
  SELECT COUNT(*) AS households, SUM(monetary_value) AS revenue
  FROM `fmcg_analytics.customer_360_kmeans`
),
kmeans AS (
  SELECT
    'kmeans_segment' AS segment_dimension,
    kmeans_segment AS segment_name,
    COUNT(*) AS household_count,
    ROUND(SUM(monetary_value), 2) AS observed_revenue,
    ROUND(AVG(frequency_baskets), 2) AS avg_baskets,
    ROUND(AVG(recency_days), 2) AS avg_recency_days,
    ROUND(AVG(coupon_basket_rate), 4) AS avg_coupon_basket_rate
  FROM `fmcg_analytics.customer_360_kmeans`
  GROUP BY kmeans_segment
),
rfm AS (
  SELECT
    'rfm_segment' AS segment_dimension,
    rfm_segment AS segment_name,
    COUNT(*) AS household_count,
    ROUND(SUM(monetary_value), 2) AS observed_revenue,
    ROUND(AVG(frequency_baskets), 2) AS avg_baskets,
    ROUND(AVG(recency_days), 2) AS avg_recency_days,
    ROUND(AVG(coupon_basket_rate), 4) AS avg_coupon_basket_rate
  FROM `fmcg_analytics.customer_360_kmeans`
  GROUP BY rfm_segment
),
combined AS (
  SELECT * FROM kmeans
  UNION ALL
  SELECT * FROM rfm
)
SELECT
  c.*,
  SAFE_DIVIDE(c.household_count, t.households) AS household_share,
  SAFE_DIVIDE(c.observed_revenue, t.revenue) AS revenue_share,
  IF(c.segment_dimension = 'kmeans_segment', 'model_based_assignment', 'observed_rfm_rule') AS evidence_type
FROM combined AS c
CROSS JOIN totals AS t;

SELECT *
FROM `fmcg_analytics.mart_customer_segment_performance`
ORDER BY segment_dimension, observed_revenue DESC;
