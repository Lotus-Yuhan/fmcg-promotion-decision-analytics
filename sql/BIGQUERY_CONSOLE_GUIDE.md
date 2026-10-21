# BigQuery Console Guide

This guide reproduces the cloud SQL layer without publishing the restricted
source files.

## 0. Use BigQuery Sandbox

This project was validated with BigQuery Sandbox and did not require a billing
account. If Google Cloud asks for payment details or a billing upgrade, stop and
confirm that Sandbox is available for the account before continuing.

Open: <https://console.cloud.google.com/bigquery>

## 1. Create a Google Cloud project

1. Sign in to Google Cloud.
2. Create a project named `fmcg-promotion-analytics`.
3. Select `No organization` when using a personal account without a managed
   organization.
4. Wait for the project to become active, then open BigQuery Studio.

## 2. Create the dataset

1. In Explorer, locate the new project.
2. Open the project menu and select **Create dataset**.
3. Enter `fmcg_analytics` as the Dataset ID.
4. Select `Singapore (asia-southeast1)` when available.
5. Keep Google-managed encryption unless the environment requires a different
   policy.
6. Do not enable public sharing or create a public dataset.
7. Select **Create dataset**.

## 3. Upload the nine source tables

Repeat this process for each source file:

1. Select the `fmcg_analytics` dataset.
2. Select **Create table**.
3. For **Create table from**, select **Upload**.
4. Select the local file.
5. Choose `Parquet` as the file format, except for the CSV noted below.
6. Enter the table name exactly as shown in the checklist.
7. Enable schema auto-detection.
8. Confirm that the destination dataset is `fmcg_analytics`.
9. Select **Create table**, verify success, and continue with the next file.

| Done | BigQuery table | Local file | Format |
|---|---|---|---|
| [ ] | `transactions` | `data/processed/transactions.parquet` | Parquet |
| [ ] | `products` | `data/processed/products.parquet` | Parquet |
| [ ] | `beverage_transactions` | `data/processed/beverage_transactions.parquet` | Parquet |
| [ ] | `campaign_table` | `data/processed/campaign_table.parquet` | Parquet |
| [ ] | `campaign_desc` | `data/processed/campaign_desc.parquet` | Parquet |
| [ ] | `coupon_redempt` | `data/processed/coupon_redempt.parquet` | Parquet |
| [ ] | `coupon` | `data/processed/coupon.parquet` | Parquet |
| [ ] | `customer_360_kmeans` | `data/local_exports/customer_360_kmeans.csv` | CSV |
| [ ] | `matched_promotion_event_panel` | `data/processed/matched_promotion_event_panel.parquet` | Parquet |

For `customer_360_kmeans.csv`, select `CSV`, enable schema auto-detection and
set **Header rows to skip** to `1`.

These files are restricted local inputs. Keep the dataset private, and do not
commit or redistribute the files.

## 4. Verify the uploads

Expand `fmcg_analytics` in Explorer and confirm that all nine tables are
present. Open the `transactions` table details and confirm approximately
`2,595,732` rows.

## 5. Run the SQL modules

1. In BigQuery Studio, select **Compose new query**.
2. Open the corresponding local SQL file and copy its complete contents into
   the query editor.
3. Select **Run**.
4. Confirm a successful job and the expected output table.
5. Repeat in the following order:

   1. `00_source_contract.sql`
   2. `01_data_quality.sql`
   3. `02_customer_segmentation.sql`
   4. `03_coupon_performance.sql`
   5. `04_promotion_effectiveness.sql`
   6. `05_executive_kpis.sql`

## 6. Validate the result

After all six modules finish, the dataset should contain analytical tables with
the `mart_` prefix. Review at least the following:

- `mart_data_quality`: no check has `FAIL` status.
- `mart_executive_kpis`: observed store sales are approximately $8.06M and the
  beverage share is approximately 8.2%.
- `mart_coupon_type_performance`: Type A has the highest average campaign
  penetration.
- `mart_customer_segment_performance`: High-Value Frequent represents
  approximately 45.2% of households and 79.0% of observed revenue.
- `mart_promotion_summary`: 423 matched events and approximately 0.36
  incremental promotion-week units per event.

If a job fails, preserve the complete error message before changing any table
name, schema or SQL statement.
