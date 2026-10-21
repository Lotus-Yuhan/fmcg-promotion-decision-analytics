# BigQuery 中文操作步骤

## 0. 不要开通付费试用

如果页面显示“免费试用”、“结算账号”或要求填写银行卡，请关闭该页面。
本项目使用 BigQuery Sandbox，不需要银行卡。

正确入口：https://console.cloud.google.com/bigquery

## 1. 创建 Sandbox 项目

1. 使用你的 Google 账号登录。
2. 国家/地区选择 `Malaysia`。
3. 阅读并同意服务条款后，点击“同意并继续”。
4. 点击“创建项目”。
5. Project name 填写 `fmcg-promotion-analytics`。
6. 如果不是学校/公司管理账号，Organization 选择 `No organization`。
7. 点击“创建”，等待返回 BigQuery Studio。

## 2. 创建 Dataset

1. 在左侧 Explorer 找到刚创建的项目。
2. 点击项目右侧的三个点，选择 `Create dataset`。
3. Dataset ID 填写 `fmcg_analytics`。
4. Location 选择 `Singapore (asia-southeast1)`（如果界面可用）。
5. 保持 Google-managed encryption 默认设置。
6. 不要勾选外部数据集，不要设置公开共享。
7. 点击 `Create dataset`。

## 3. 上传九张源表

每张表都使用同一流程：

1. 点击 `fmcg_analytics` Dataset。
2. 点击 `Create table`。
3. Create table from 选择 `Upload`。
4. 选择本地文件。
5. File format 选择 `Parquet`；CSV 文件例外。
6. Table 名称必须与下表完全一致。
7. Schema 选择 `Auto detect`。
8. 目标 Dataset 确认为 `fmcg_analytics`。
9. 点击 `Create table`，成功后再上传下一张。

| 完成 | Table 名称 | 本地文件 | 格式 |
|---|---|---|---|
| ☐ | `transactions` | `data/processed/transactions.parquet` | Parquet |
| ☐ | `products` | `data/processed/products.parquet` | Parquet |
| ☐ | `beverage_transactions` | `data/processed/beverage_transactions.parquet` | Parquet |
| ☐ | `campaign_table` | `data/processed/campaign_table.parquet` | Parquet |
| ☐ | `campaign_desc` | `data/processed/campaign_desc.parquet` | Parquet |
| ☐ | `coupon_redempt` | `data/processed/coupon_redempt.parquet` | Parquet |
| ☐ | `coupon` | `data/processed/coupon.parquet` | Parquet |
| ☐ | `customer_360_kmeans` | `data/local_exports/customer_360_kmeans.csv` | CSV |
| ☐ | `matched_promotion_event_panel` | `data/processed/matched_promotion_event_panel.parquet` | Parquet |

CSV 例外设置：上传 `customer_360_kmeans.csv` 时，File format 选择 `CSV`，
勾选 Auto detect，Header rows to skip 填写 `1`。

## 4. 检查上传结果

在 Explorer 展开 `fmcg_analytics`，应该看到九张表。先点击
`transactions` 的 Details，确认 Number of rows 约为 `2,595,732`。

## 5. 运行 SQL

1. 在 BigQuery Studio 点击 `+ Compose new query`。
2. 打开本地 `sql/bigquery/00_source_contract.sql`，全选并复制内容。
3. 粘贴到查询编辑器，点击 `Run`。
4. 确认显示绿色成功状态并产生新表。
5. 按 `00` 到 `05` 的顺序重复操作。

运行顺序：

1. `00_source_contract.sql`
2. `01_data_quality.sql`
3. `02_customer_segmentation.sql`
4. `03_coupon_performance.sql`
5. `04_promotion_effectiveness.sql`
6. `05_executive_kpis.sql`

## 6. 最终检查

运行完成后，`fmcg_analytics` 中应该出现以 `mart_` 开头的结果表。
重点检查：

- `mart_data_quality`：没有 `FAIL`。
- `mart_executive_kpis`：总销售约 805.7 万美元，饮料占比约 8.2%。
- `mart_coupon_type_performance`：Type A 的平均活动渗透率最高。
- `mart_customer_segment_performance`：High-Value Frequent 占客户约 45.2%，收入约 79.0%。
- `mart_promotion_summary`：423 个匹配事件，促销周增量约 0.36 件。

如果出现红色错误，请截图保留完整错误信息，不要自行修改表名或 SQL。
