-- Coupon performance uses household-campaign exposure as the denominator.
-- A household redeeming multiple coupons in one campaign counts once in the
-- penetration rate and all transactions in the transaction-rate measure.

CREATE OR REPLACE TABLE `fmcg_analytics.mart_coupon_campaign_performance` AS
WITH targets AS (
  SELECT DISTINCT campaign, household_key
  FROM `fmcg_analytics.campaign_table`
),
redemptions AS (
  SELECT
    campaign,
    household_key,
    COUNT(*) AS redemption_transactions
  FROM `fmcg_analytics.coupon_redempt`
  GROUP BY campaign, household_key
),
coupon_definitions AS (
  SELECT
    campaign,
    COUNT(DISTINCT coupon_upc) AS coupon_upcs_defined,
    COUNT(DISTINCT product_id) AS coupon_products_covered
  FROM `fmcg_analytics.coupon`
  GROUP BY campaign
)
SELECT
  t.campaign,
  CASE d.description
    WHEN 'TypeA' THEN 'Type A'
    WHEN 'TypeB' THEN 'Type B'
    WHEN 'TypeC' THEN 'Type C'
    ELSE d.description
  END AS campaign_type,
  COUNT(DISTINCT t.household_key) AS targeted_households,
  COUNT(*) AS household_campaign_exposures,
  COUNTIF(r.redemption_transactions IS NOT NULL) AS redeeming_households,
  COALESCE(SUM(r.redemption_transactions), 0) AS redemption_transactions,
  SAFE_DIVIDE(COUNTIF(r.redemption_transactions IS NOT NULL), COUNT(*)) AS redemption_penetration,
  SAFE_DIVIDE(COALESCE(SUM(r.redemption_transactions), 0) * 100, COUNT(*)) AS redemptions_per_100_targets,
  d.start_day,
  d.end_day,
  d.end_day - d.start_day + 1 AS campaign_duration_days,
  c.coupon_upcs_defined,
  c.coupon_products_covered,
  'observed_behavior' AS evidence_type
FROM targets AS t
LEFT JOIN redemptions AS r USING (campaign, household_key)
LEFT JOIN `fmcg_analytics.campaign_desc` AS d USING (campaign)
LEFT JOIN coupon_definitions AS c USING (campaign)
GROUP BY t.campaign, d.description, d.start_day, d.end_day,
         c.coupon_upcs_defined, c.coupon_products_covered;

CREATE OR REPLACE TABLE `fmcg_analytics.mart_coupon_type_performance` AS
SELECT
  campaign_type,
  SUM(targeted_households) AS targeted_household_campaigns,
  SUM(redeeming_households) AS redeemed_household_campaigns,
  SUM(redemption_transactions) AS redemption_transactions,
  SAFE_DIVIDE(SUM(redeeming_households), SUM(targeted_households)) AS weighted_target_redemption_penetration,
  AVG(redemption_penetration) AS avg_campaign_redemption_penetration,
  'observed_behavior' AS evidence_type
FROM `fmcg_analytics.mart_coupon_campaign_performance`
GROUP BY campaign_type;

CREATE OR REPLACE TABLE `fmcg_analytics.mart_coupon_segment_performance` AS
WITH targets AS (
  SELECT DISTINCT campaign, household_key
  FROM `fmcg_analytics.campaign_table`
),
redemptions AS (
  SELECT campaign, household_key, COUNT(*) AS redemption_transactions
  FROM `fmcg_analytics.coupon_redempt`
  GROUP BY campaign, household_key
)
SELECT
  c.kmeans_segment AS segment_name,
  COUNT(DISTINCT t.household_key) AS targeted_households,
  COUNT(*) AS household_campaign_exposures,
  COUNTIF(r.redemption_transactions IS NOT NULL) AS redeemed_household_campaigns,
  COALESCE(SUM(r.redemption_transactions), 0) AS redemption_transactions,
  SAFE_DIVIDE(COUNTIF(r.redemption_transactions IS NOT NULL), COUNT(*)) AS redemption_penetration,
  SAFE_DIVIDE(COALESCE(SUM(r.redemption_transactions), 0) * 100, COUNT(*)) AS redemptions_per_100_exposures,
  'observed_behavior' AS evidence_type
FROM targets AS t
JOIN `fmcg_analytics.customer_360_kmeans` AS c USING (household_key)
LEFT JOIN redemptions AS r USING (campaign, household_key)
GROUP BY c.kmeans_segment;

SELECT *
FROM `fmcg_analytics.mart_coupon_type_performance`
ORDER BY avg_campaign_redemption_penetration DESC;
