# BigQuery Cloud Run Validation

## Run metadata

- Run date: 2026-10-21
- Platform: BigQuery Sandbox
- Region: `asia-southeast1`
- Dataset: `fmcg_analytics`
- SQL dialect: GoogleSQL
- Script sequence: `00_source_contract.sql` through `05_executive_kpis.sql`

## Execution result

All six scripts completed successfully and created the intended source-contract,
quality-control and analytical mart tables.

Key data-quality reconciliations:

| Check | Observed | Expected | Status |
|---|---:|---:|---|
| Transaction rows | 2,595,732 | 2,595,732 | PASS |
| Unique households | 2,500 | 2,500 | PASS |
| Targeted household-campaign exposures | 7,208 | 7,208 | PASS |
| Matched event-panel rows | 3,807 | 3,807 | PASS |
| Missing transaction keys | 0 | 0 | PASS |
| Missing customer segments | 0 | 0 | PASS |
| Orphan product-transaction rows | 0 | 0 | PASS |

Final `mart_executive_kpis` reconciliation:

| Metric | BigQuery value | Display value |
|---|---:|---:|
| Total store sales | 8,057,463.08 | $8.06M |
| Beverage sales | 661,332.87 | $661K |
| Beverage sales share | 0.082077 | 8.2% |
| Household count | 2,500 | 2.5K |
| Targeted coupon redemption penetration | 0.123335 | 12.3% |
| High-Value Frequent household share | 0.4516 | 45.2% |
| High-Value Frequent revenue share | 0.789645 | 79.0% |
| Matched promotion events | 423 | 423 |
| Incremental units per event | 0.361111 | +0.36 |
| Incremental revenue per event | 0.546678 | +$0.55 |

## Evidence boundary

- Sales, customer and coupon metrics are observed behavior.
- K-Means segment labels are model-based assignments.
- Matched promotion effects are quasi-experimental estimates, not randomised
  trial results.
- Profit and ROI remain assumption-only scenarios because actual gross margin
  and execution-cost inputs are unavailable.

The cloud tables are private analytical inputs and outputs. Licensed dunnhumby
row-level data remain excluded from Git.
