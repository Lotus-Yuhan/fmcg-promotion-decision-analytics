# BigQuery SQL Analytics Layer

Step-by-step console guide: [BIGQUERY_CONSOLE_GUIDE.md](BIGQUERY_CONSOLE_GUIDE.md)

Cloud execution status: all six scripts were run successfully in BigQuery
Sandbox on 2026-10-21 (`asia-southeast1`). The final KPI table reconciled to
the local Python and Power BI outputs; see
[`../outputs/validation/bigquery_cloud_run.md`](../outputs/validation/bigquery_cloud_run.md).

This folder reproduces the portfolio's core business findings in GoogleSQL.
It is intentionally separate from the Python modelling pipeline: Python builds
the matched-event and K-Means assignments, while SQL audits, aggregates and
turns those inputs into decision tables.

## Why BigQuery

BigQuery gives the project a cloud data-warehouse layer without requiring a
server. The processed source files are small enough for an interview-scale
demo, and Parquet preserves types better than re-uploading the raw CSV files.

Do not make the dataset public. The dunnhumby source data are licensed inputs
and are intentionally excluded from Git.

## 1. Create the dataset

In BigQuery Studio, create a dataset named `fmcg_analytics`. Keep all source
tables and query outputs in the same location.

## 2. Upload the source tables

Use **Create table -> Upload**, choose the file below, select the stated table
name, and enable schema auto-detection.

| BigQuery table | Local file | Purpose |
|---|---|---|
| `transactions` | `data/processed/transactions.parquet` | Store-wide sales and Customer 360 |
| `products` | `data/processed/products.parquet` | Product reference and join-quality checks |
| `beverage_transactions` | `data/processed/beverage_transactions.parquet` | Beverage category and promotion flags |
| `campaign_table` | `data/processed/campaign_table.parquet` | Targeted household-campaign exposures |
| `campaign_desc` | `data/processed/campaign_desc.parquet` | Campaign type and active dates |
| `coupon_redempt` | `data/processed/coupon_redempt.parquet` | Observed coupon redemptions |
| `coupon` | `data/processed/coupon.parquet` | Coupon-product definitions |
| `customer_360_kmeans` | `data/local_exports/customer_360_kmeans.csv` | Local model assignments for segment reporting |
| `matched_promotion_event_panel` | `data/processed/matched_promotion_event_panel.parquet` | Matched DiD/event-study input |

`customer_360_kmeans.csv` and the Parquet files are local, Git-ignored inputs.
They must not be committed or redistributed.

## 3. Run the SQL files in order

1. `00_source_contract.sql` records the table grain, evidence type and expected
   row counts.
2. `01_data_quality.sql` checks completeness, duplicates, key relationships and
   matched-panel integrity.
3. `02_customer_segmentation.sql` creates an independent SQL RFM table and
   summarizes the validated K-Means assignments used by Power BI.
4. `03_coupon_performance.sql` measures redemption by campaign type and customer
   segment using targeted household-campaign exposure as the denominator.
5. `04_promotion_effectiveness.sql` summarizes matched event-study effects and
   category heterogeneity.
6. `05_executive_kpis.sql` creates one interview-ready KPI table.

The scripts use `fmcg_analytics.table_name`, so no project ID needs to be typed
when the correct Google Cloud project is selected in BigQuery Studio.

## 4. Reconciliation targets

After all scripts run, the outputs should reconcile to these current-project
benchmarks:

| Check | Expected result |
|---|---:|
| Transaction rows | 2,595,732 |
| Unique households | 2,500 |
| Observed store sales | about $8.06M |
| Beverage sales | about $661K |
| Targeted household-campaign exposures | 7,208 |
| Overall targeted redemption penetration | about 12.3% |
| Average campaign penetration by type | Type A 14.2%, Type C 9.1%, Type B 7.8% |
| High-Value Frequent household share | about 45.2% |
| High-Value Frequent revenue share | about 79.0% |
| Matched promotion events | 423 |
| Promotion-week incremental units per event | about +0.36 |
| Promotion-week incremental revenue per event | about +$0.55 |

The SQL confidence intervals use a simple event-level normal approximation for
transparent cloud verification. The Power BI headline interval and p-value are
the Python cluster-bootstrap estimates and remain the primary inferential
result.

## Evidence boundary

- Transaction, customer and coupon metrics are observed behavior.
- Matched event-study metrics are quasi-experimental estimates, not randomised
  trial results.
- ROI and profit are excluded because actual margin and execution-cost inputs
  are unavailable; those numbers remain assumption-only Power BI scenarios.
