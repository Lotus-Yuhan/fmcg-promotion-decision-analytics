# Project Development Log and Release Record

## 1. Objective

This project addresses an FMCG retail decision problem: when promotion budget
is limited, which categories, campaigns and customer groups should receive
investment, and how should observed sales, estimated incrementality and
assumption-dependent returns be distinguished?

The deliverable is an auditable analytical chain rather than a standalone
dashboard:

`restricted source data -> Python processing and modelling -> quality controls -> BigQuery SQL marts -> Power BI decision reporting -> Git/GitHub version control`

Core outputs use four evidence labels so that results with different meanings
are not mixed:

| Evidence label | Meaning | Example |
|---|---|---|
| `observed_behavior` | Direct aggregation of transaction, campaign or redemption records | Sales, household count, coupon-redemption penetration |
| `model_based_assignment` | Customer labels produced by an algorithm | K-Means customer segments |
| `quasi_experimental_estimate` | Promotion incrementality estimated through matching and Difference-in-Differences | Approximately 0.36 incremental units per event |
| `assumption_only_scenario` | Scenario dependent on cost, margin and scaling assumptions | ROI, net contribution and break-even multiplier |

## 2. Platforms and design rationale

| Platform or method | Role in the project | Why it was selected |
|---|---|---|
| dunnhumby Complete Journey | Anonymous household, transaction, product, campaign and coupon inputs | The structure resembles a real retail data environment; the restricted inputs remain local or in a private cloud dataset |
| Python, pandas and PyArrow | Data cleaning, joins, Customer 360, retention, promotion panels and Power BI exports | Reproducible processing, automated checks and efficient Parquet support |
| scikit-learn | K-Means segmentation, scaling and stability assessment | Supports interpretable assignments plus silhouette and adjusted Rand index validation |
| Matching, DiD, event study and bootstrap | Promotion incrementality analysis | Separates promoted-sales correlation from plausible incremental impact and supports balance, pre-trend and placebo diagnostics |
| Google BigQuery Sandbox and GoogleSQL | Cloud data-quality layer and analytical marts | Demonstrates warehouse SQL and makes source contracts, quality checks and KPI reconciliation auditable |
| Power BI Desktop, PBIP and DAX | Four-page interactive decision report | Separates observed, model-based, quasi-experimental and assumption-only outputs; PBIP also supports text-based review |
| Git and GitHub | Version control, attribution and portfolio delivery | Keeps code, methods, validation evidence and report definitions traceable while excluding restricted data |

## 3. Implementation record

### Stage A: Source, scope and publication boundary

1. Preserved the MIT licence and baseline attribution in
   `THIRD_PARTY_NOTICES.md`.
2. Classified raw dunnhumby inputs as local or private-cloud data; `data/raw/`
   and other fine-grained extracts are excluded from Git.
3. Split the business question into descriptive, incremental and decision
   layers to avoid presenting correlation as causation.

### Stage B: Python data foundation and quality controls

1. Cleaned and joined transaction, product, campaign, coupon and redemption
   data.
2. Built transaction-, product-, household- and product-store-week analytical
   datasets.
3. Checked row counts, keys, missing values, orphan records, invalid values and
   sales reconciliation.
4. Kept raw tables, Parquet intermediates and household-level outputs local;
   only code, methods and approved aggregates are included in the repository.

### Stage C: Customer 360, RFM, cohorts and K-Means

1. Created a one-row-per-household Customer 360 table with recency, frequency,
   monetary value, basket value, active weeks, discount use and coupon use.
2. Built first-observed-purchase cohorts in fixed 30-day periods. P00 is marked
   as left-censored, and cohorts with fewer than 30 households are excluded from
   the main comparison.
3. Compared K=2 through K=8, selected K=3 using quantitative diagnostics and
   business interpretability, and tested seed and time-window stability.
4. Produced three decision-oriented groups: High-Value Frequent, Developing
   Occasional and Dormant Low-Value.

### Stage D: Coupon and commercial decision layer

1. Corrected the coupon denominator: the 124,548 rows in `coupon` represent
   coupon-product eligibility mappings, not coupon issuances.
2. Used 7,208 unique household-campaign targeted exposures as the denominator,
   producing a 12.33% targeted-household redemption penetration rate.
3. Produced aggregate campaign-type, segment and category views without
   interpreting non-random targeting differences as causal segment response.

### Stage E: Promotion incrementality

1. Created a four-week pre/post event window and removed overlapping campaigns.
2. Matched treated events to unexposed controls within category using common
   support and a distance threshold.
3. Ran matched Difference-in-Differences, an event study, product-cluster
   bootstrap inference, pre-trend checks and placebo tests.
4. Labelled the result as quasi-experimental rather than randomised evidence.

### Stage F: Power BI decision report

The PBIP project contains four pages:

| Page | Decision question |
|---|---|
| Executive Summary | What are the main sales, category, redemption and management findings? |
| Customer Growth & Segmentation | Which customers create value, and do they remain active? |
| Promotion Incrementality | How much short-term lift is plausibly attributable to promotion? |
| Budget Scenario Planner | Under explicit margin, cost, scale and budget assumptions, when does the scenario break even? |

Each page displays its evidence type. The ROI page uses single-select parameters
so that cards, sensitivity lines and explanatory text refer to the same
assumption tuple.

### Stage G: BigQuery cloud SQL layer

The cloud layer was completed on 2026-10-21:

1. Created a private `fmcg_analytics` dataset in BigQuery Sandbox in
   `asia-southeast1`.
2. Uploaded nine restricted local source tables. The dataset was not made
   public, and the files were not committed to GitHub.
3. Ran `sql/bigquery/00_source_contract.sql` through
   `05_executive_kpis.sql` in order:
   - 00: source contracts, grains and expected row counts;
   - 01: data-quality checks and reconciliation;
   - 02: customer RFM and segment performance;
   - 03: coupon campaign, type and segment performance;
   - 04: matched promotion events and incremental effects;
   - 05: executive KPI summary.
4. All six scripts completed successfully, and the cloud results reconciled to
   the Python and Power BI outputs. See
   `outputs/validation/bigquery_cloud_run.md`.

## 4. Decision findings

### 4.1 Revenue structure

- Observed store sales are approximately **$8.06M**; beverage sales are about
  **$661K**, or **8.2%** of total sales.
- Carbonated soft drinks contribute approximately **59.2%** of beverage sales,
  and juice contributes approximately **22.8%**.
- These categories are the most defensible candidates for controlled promotion
  expansion tests rather than an undifferentiated budget increase.

### 4.2 Customer value and retention

- High-Value Frequent households represent **45.2%** of households and
  contribute **79.0%** of observed whole-store revenue.
- About **81.1%** of comparable cohorts remain active in the twelfth 30-day
  period after first observed purchase. The panel contains frequent shoppers,
  and P00 is left-censored, so this is not a general new-customer retention rate.
- Retention activity should prioritize High-Value Frequent households;
  Developing Occasional households are candidates for reactivation or
  frequency tests. Large untargeted investment in Dormant Low-Value households
  is not supported by the current evidence.

### 4.3 Coupon performance

- Overall targeted redemption penetration is **12.33%**.
- Observed penetration is **13.78%** for High-Value Frequent and **4.13%** for
  Developing Occasional households.
- Average campaign penetration is approximately **14.2%** for Type A,
  **9.1%** for Type C and **7.8%** for Type B.
- These are observed targeting and redemption differences. Non-random campaign
  assignment prevents a causal claim that one segment is inherently more
  coupon-responsive.

### 4.4 Promotion incrementality

- Across 423 matched events, the promotion week adds approximately **0.36
  units** and **$0.55 revenue** per product-store event.
- The bootstrap 95% interval for incremental units is approximately
  **[0.14, 0.65]**, with p approximately **0.007**. The pre-trend test has p
  approximately **0.442**, so the analysis does not detect clear pre-treatment
  divergence; it does not prove parallel trends.
- Carbonated soft drinks add approximately **0.39 units per event**, and juice
  adds approximately **0.27 units per event**. Both are candidates for
  controlled scaling tests.
- Later event-study intervals cross zero, so the current evidence does not
  establish a persistent effect.

### 4.5 ROI and budget scenario

- Under the default point-estimate, 10x scale, 30% margin, $5 event cost and
  $1,000 budget assumptions, net contribution is approximately **-$671.99** and
  ROI is approximately **-67.2%**.
- Break-even requires a panel-to-total-sales multiplier of approximately
  **30.5x**.
- Actual margin, execution cost and full-store scaling data are unavailable.
  This is therefore an assumption stress test, not evidence of realized loss.
- The decision recommendation is to run controlled tests in carbonated soft
  drinks and juice, obtain actual margin and execution-cost data, and then
  recalculate ROI before broad budget expansion.

## 5. Portfolio evidence

This repository demonstrates the ability to:

- build a reproducible Python pipeline from restricted business data;
- validate grain, denominators, reconciliation, stability and evidence limits;
- implement a BigQuery SQL layer from source contracts through executive KPIs;
- distinguish descriptive facts, model assignments, quasi-experimental
  estimates and commercial assumptions;
- translate technical results into a Power BI decision narrative while
  retaining caveats; and
- manage attribution, reproducibility and public-data boundaries with Git and
  GitHub.

## 6. Release audit and current repository state

The original working repository was made private after a release audit found
fine-grained household and product/SKU extracts in inherited history. Removing
files from the latest commit would not remove those historical blobs.

The current repository therefore uses a new, clean Git history created from an
audited snapshot. Its initial private push was completed on 2026-10-21. The
release boundary is deliberately conservative:

- `.gitignore` excludes `data/raw/`, `data/processed/` and
  `data/local_exports/`;
- household-level exports, transaction facts, product-dimension extracts,
  SKU-level outputs, PBIX binaries and Power BI caches are excluded;
- tracked data files contain approved aggregates or validation summaries;
- no API keys, passwords or private keys were found in the release scan;
- the original MIT licence and contributor attribution are retained;
- the BigQuery dataset and its nine source tables remain private; and
- the Power BI `DataFolderPath` is a portable parameter rather than a
  contributor-specific absolute path.

The dunnhumby [Source Files](https://www.dunnhumby.com/source-files/) page
describes classroom, research and algorithm-development uses but does not
expressly grant public redistribution rights for source tables or fine-grained
extracts. This repository therefore publishes code, methods, charts and small
aggregates, but not household-, transaction-, product- or SKU-level data. This
is a conservative project-control decision, not legal advice. A broader release
would require checking the current
[terms and conditions](https://www.dunnhumby.com/terms-and-conditions/) and, if
needed, obtaining written permission from `sourcefiles@dunnhumby.com`.

## 7. Public-release checklist

Before changing repository visibility from private to public:

1. Verify all Markdown links and English public-facing documentation.
2. Run Python syntax, quality and reconciliation checks.
3. Parse and review all six GoogleSQL scripts and retain the BigQuery execution
   record.
4. Rebuild the PBIP project and verify DAX, default-scenario arithmetic and page
   layout.
5. Scan the complete current Git history for secrets, absolute paths,
   fine-grained data and oversized files.
6. Review the GitHub-rendered README, file tree, charts, attribution and author
   information.
7. Obtain an explicit owner decision before changing repository visibility.

The repository remains private until the owner completes the final review and
explicitly approves public release.
