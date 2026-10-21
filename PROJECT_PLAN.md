# FMCG Promotion Causal Analytics — Project Plan

## Business Question

How should an FMCG or grocery retailer allocate limited promotion budgets across products, stores and customer segments?

## Project Objectives

1. Build a reproducible SQL and Python analytics pipeline.
2. Create a household-level Customer 360 table.
3. Develop RFM, cohort retention and K-Means segmentation.
4. Estimate incremental promotion effects using matched Difference-in-Differences and event-study diagnostics.
5. Translate results into promotion and budget recommendations.
6. Build a four-page Power BI decision dashboard.

## Planned Deliverables

- SQL data model and data-quality checks
- Customer 360 analytical table
- RFM and K-Means customer segmentation
- Cohort retention analysis
- Promotion treatment and control panel
- Matching balance diagnostics
- Difference-in-Differences estimates
- Parallel-trends and placebo tests
- Power BI dashboard
- Executive business report

## Causal Boundary

The original promotion lift is descriptive rather than causal. Causal claims will only be made when treatment-control comparability, parallel trends and robustness checks are sufficiently supported.

## Profit and ROI Boundary

The dataset does not contain complete product cost and promotion execution cost information. Profit and ROI outputs will therefore be presented only as assumption-based sensitivity scenarios.
