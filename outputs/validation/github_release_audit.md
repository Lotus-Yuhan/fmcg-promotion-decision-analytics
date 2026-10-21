# GitHub Release Privacy Audit

## Audit metadata

- Audit date: 2026-10-21
- Local branch: `main`
- Original working repository: private archive retained separately
- Current private repository: `Lotus-Yuhan/fmcg-promotion-decision-analytics`
- Release structure: clean `main` history with no inherited commits
- Initial private push: completed on 2026-10-21
- Recommended release method: review this clean private release candidate before any visibility change

## Public release boundary

The public portfolio may contain:

- Python source code, SQL and unexecuted notebooks;
- method and data-dictionary documentation;
- PBIP/PBIR/TMDL source that reads only approved aggregates;
- category, campaign, cohort, segment, validation and scenario aggregates;
- charts that do not expose household, transaction, product or SKU identifiers;
- BigQuery execution metadata and reconciled headline KPIs.

The public portfolio must not contain:

- `data/raw/`, `data/processed/` or `data/local_exports/`;
- household-level or transaction-level exports;
- product-dimension and SKU-level tabular extracts;
- charts that display source product identifiers;
- BigQuery source uploads, PBIX binaries, caches, preview screenshots or local backups;
- credentials, API keys, private keys, account identifiers or contributor-specific absolute paths.

## Excluded local artifacts

| Artifact | Reason | Local file retained? |
|---|---|---|
| `data/powerbi_exports/dim_households.csv` | Household-level analytical export | Yes |
| `data/powerbi_exports/fact_transactions_beverage.csv` | Transaction-level fact table | Yes if generated locally |
| `data/powerbi_exports/dim_products_beverage.csv` | Source-derived product dimension | Yes |
| `data/powerbi_exports/promotion_performance.csv` | Product-level promotion results | Yes |
| `data/powerbi_exports/sku_sales_contribution.csv` | SKU-level commercial results | Yes |
| `outputs/charts/top20_lift.png` | Displays source product IDs | Yes |
| `outputs/charts/top20_lift_products.png` | Displays source product IDs | Yes |
| BigQuery upload files | Licensed row-level cloud inputs | Yes, private cloud/local only |

## Validation completed

- Five quality files contain 45 checks; failed checks: 0.
- All six BigQuery GoogleSQL files parse successfully.
- Python source and build scripts compile successfully.
- The five tracked notebooks contain no executed cells or embedded outputs.
- The current-tree pattern scan found no private keys, API keys, passwords or contributor-specific absolute paths.
- Power BI currently loads only approved aggregate CSV inputs.
- `data/powerbi_exports/` contains 15 aggregate CSVs. The largest has 243
  scenario rows; none contains `household_key`, `product_id`, `store_id`,
  `basket_id`, a SKU identifier or transaction-level records.
- `household_segments.csv` contains four segment-level rows, not household-level
  records; `category_decision_scorecard.csv` contains seven category-level rows
  and product counts rather than product identifiers.
- Public-facing Markdown documentation uses English names and content, and its
  local links resolve.
- The GitHub About description and six portfolio topics are configured while
  the repository remains private.
- Current tracked files are small; no unexpectedly large repository object is required for the clean snapshot.
- The independently copied clean candidate contains none of the forbidden paths and no CSV headed by `household_key`, `product_id`, `store_id` or `basket_id`.

## Historical limitation

Fine-grained files exist in the old Git history. Making the repository private controls current access but does not remove old blobs from its history or from any prior copies. A clean new repository is therefore preferable to turning this same history public again.

## Release gate

Before any public push:

1. [x] Create a new empty repository with a distinct name and keep it Private during staging.
2. [x] Copy only the sanitised current snapshot; do not copy the old `.git` directory.
3. [x] Initialise a new Git history with zero inherited commits.
4. [x] Run the privacy, quality, SQL, Python and link audits against the clean candidate.
5. [x] Obtain owner confirmation of the first-commit file manifest.
6. [x] Create the first local commit and push it to the new repository while Private.
7. [x] Inspect the GitHub file list and README rendering; correct the public-facing English documentation.
8. [ ] Obtain final owner confirmation before changing the new repository to Public.

No force-push, history rewrite or repository-visibility change is authorised by
this audit alone.
