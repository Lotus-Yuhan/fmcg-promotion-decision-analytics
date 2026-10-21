-- Promotion effectiveness starts from the matched event panel created by the
-- documented Python matching workflow. SQL summarizes effects; it does not
-- claim that observational promotion flags are randomized treatment.

CREATE OR REPLACE TABLE `fmcg_analytics.mart_promotion_event_study` AS
WITH weekly AS (
  SELECT
    relative_week,
    COUNT(DISTINCT event_id) AS matched_events,
    AVG(event_study_units) AS incremental_units_per_event,
    AVG(event_study_revenue) AS incremental_revenue_per_event,
    STDDEV_SAMP(event_study_units) AS units_sd,
    STDDEV_SAMP(event_study_revenue) AS revenue_sd
  FROM `fmcg_analytics.matched_promotion_event_panel`
  GROUP BY relative_week
)
SELECT
  relative_week,
  matched_events,
  incremental_units_per_event,
  incremental_revenue_per_event,
  incremental_units_per_event - 1.96 * SAFE_DIVIDE(units_sd, SQRT(matched_events)) AS units_ci_low_normal,
  incremental_units_per_event + 1.96 * SAFE_DIVIDE(units_sd, SQRT(matched_events)) AS units_ci_high_normal,
  incremental_revenue_per_event - 1.96 * SAFE_DIVIDE(revenue_sd, SQRT(matched_events)) AS revenue_ci_low_normal,
  incremental_revenue_per_event + 1.96 * SAFE_DIVIDE(revenue_sd, SQRT(matched_events)) AS revenue_ci_high_normal,
  'quasi_experimental_estimate' AS evidence_type,
  'Normal CI for SQL audit; Power BI headline uses cluster bootstrap' AS interval_note
FROM weekly;

CREATE OR REPLACE TABLE `fmcg_analytics.mart_promotion_category_effects` AS
SELECT
  beverage_category,
  COUNT(DISTINCT event_id) AS matched_events,
  AVG(event_study_units) AS incremental_units_per_event,
  AVG(event_study_revenue) AS incremental_revenue_per_event,
  'quasi_experimental_estimate' AS evidence_type
FROM `fmcg_analytics.matched_promotion_event_panel`
WHERE relative_week = 0
GROUP BY beverage_category
HAVING COUNT(DISTINCT event_id) >= 30;

CREATE OR REPLACE TABLE `fmcg_analytics.mart_promotion_summary` AS
WITH promotion_week AS (
  SELECT
    COUNT(DISTINCT event_id) AS matched_events,
    COUNT(DISTINCT product_id) AS matched_products,
    AVG(event_study_units) AS incremental_units_per_event,
    AVG(event_study_revenue) AS incremental_revenue_per_event,
    AVG(treated_pre_units) AS treated_pre_units
  FROM `fmcg_analytics.matched_promotion_event_panel`
  WHERE relative_week = 0
),
preperiod_week AS (
  SELECT
    relative_week,
    AVG(event_study_units) AS avg_week_effect
  FROM `fmcg_analytics.matched_promotion_event_panel`
  WHERE relative_week BETWEEN -4 AND -1
  GROUP BY relative_week
),
preperiod AS (
  SELECT
    AVG(avg_week_effect) AS mean_preperiod_unit_effect,
    MAX(ABS(avg_week_effect)) AS max_abs_preperiod_week_effect
  FROM preperiod_week
)
SELECT
  p.matched_events,
  p.matched_products,
  p.incremental_units_per_event,
  p.incremental_revenue_per_event,
  SAFE_DIVIDE(p.incremental_units_per_event, p.treated_pre_units) AS incremental_units_vs_preperiod,
  e.mean_preperiod_unit_effect,
  e.max_abs_preperiod_week_effect,
  'quasi_experimental_estimate' AS evidence_type,
  'Matched observational events; parallel-trend diagnostics do not prove randomization' AS interpretation_boundary
FROM promotion_week AS p
CROSS JOIN preperiod AS e;

SELECT *
FROM `fmcg_analytics.mart_promotion_event_study`
ORDER BY relative_week;
